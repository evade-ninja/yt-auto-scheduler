import argparse
import ast
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, mock_open, patch
from zoneinfo import ZoneInfo

import status_report

ROOT = Path(__file__).resolve().parents[1]
SMTP_CONFIG = {'smtp': {'server': 'smtp.example.com', 'username': 'sender@example.com',
                        'password': 'test-password', 'destination': 'reports@example.com'}}


class HttpError(Exception):
    pass


class LocalTimezone(ZoneInfo):
    def localize(self, value):
        return value.replace(tzinfo=ZoneInfo('America/Boise'))


class ReportTests(unittest.TestCase):
    def test_starttls_delivery(self):
        with patch('status_report.smtplib.SMTP') as smtp:
            status_report.send_status_report(SMTP_CONFIG, 'Run status', 'Completed')
        smtp.assert_called_once_with('smtp.example.com', 587, timeout=30)
        connection = smtp.return_value.__enter__.return_value
        connection.starttls.assert_called_once()
        connection.login.assert_called_once_with('sender@example.com', 'test-password')
        message = connection.send_message.call_args.args[0]
        self.assertEqual(message['To'], 'reports@example.com')
        self.assertEqual(message['From'], 'sender@example.com')
        self.assertEqual(message['Subject'], 'Run status')
        self.assertIn('Completed', message.get_content())
        self.assertNotIn('test-password', message.as_string())
        self.assertEqual([call[0] for call in connection.method_calls],
                         ['starttls', 'login', 'send_message'])

    def test_implicit_tls_delivery(self):
        config = {'smtp': dict(SMTP_CONFIG['smtp'], useSsl=True, fromAddress='other@example.com')}
        with patch('status_report.smtplib.SMTP_SSL') as smtp, patch('status_report.smtplib.SMTP') as plain:
            status_report.send_status_report(config, 'Status', 'Done')
        plain.assert_not_called()
        self.assertEqual(smtp.call_args.args, ('smtp.example.com', 465))
        connection = smtp.return_value.__enter__.return_value
        connection.starttls.assert_not_called()
        self.assertEqual(connection.send_message.call_args.args[0]['From'], 'other@example.com')

    def test_tls_port_mismatch_fails_before_connecting(self):
        for use_ssl, port in ((True, 587), (False, 465)):
            with self.subTest(useSsl=use_ssl, port=port):
                config = {'smtp': dict(SMTP_CONFIG['smtp'], useSsl=use_ssl, port=port)}
                with patch('status_report.smtplib.SMTP') as plain, patch('status_report.smtplib.SMTP_SSL') as secure:
                    with self.assertRaisesRegex(ValueError, 'TLS'):
                        status_report.send_status_report(config, 'Status', 'Done')
                plain.assert_not_called()
                secure.assert_not_called()

    def test_report_sent_on_unexpected_failure(self):
        with patch('status_report.send_status_report') as send, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'broken'):
                with status_report.StatusReport(SMTP_CONFIG, 'schedule.py') as report:
                    report.add('SUCCESS', 'First video created')
                    report.context = 'Second video / binding stream'
                    raise ValueError('broken')
        self.assertEqual(send.call_count, 1)
        self.assertIn('ISSUES', send.call_args.args[1])
        self.assertIn('First video created', send.call_args.args[2])
        self.assertIn('Second video / binding stream', send.call_args.args[2])
        self.assertIn('remaining operations were not attempted', send.call_args.args[2])

    def test_delivery_failure_does_not_mask_operation_failure(self):
        with patch('status_report.send_status_report', side_effect=OSError('mail unavailable')), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'operation failed'):
                with status_report.StatusReport(SMTP_CONFIG, 'test'):
                    raise ValueError('operation failed')
            with self.assertRaisesRegex(OSError, 'mail unavailable'):
                with status_report.StatusReport(SMTP_CONFIG, 'test'):
                    pass


class ScriptTests(unittest.TestCase):
    def load_functions(self, filename, config, video_list=None):
        # Exercise script functions without importing unavailable Google OAuth dependencies.
        tree = ast.parse((ROOT / filename).read_text())
        namespace = {
            'argparse': argparse, 'json': json, 'datetime': datetime, 'timedelta': timedelta,
            'pytz': SimpleNamespace(timezone=lambda name: LocalTimezone(name), utc=timezone.utc),
            'time': SimpleNamespace(sleep=MagicMock()), 'HttpError': HttpError,
            'StatusReport': status_report.StatusReport,
        }
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        exec(compile(ast.Module(body=functions, type_ignores=[]), filename, 'exec'), namespace)
        namespace['parse_args'] = lambda: SimpleNamespace(config='config.json')
        contents = {'config.json': json.dumps(config), 'videos.json': json.dumps(video_list or [])}
        namespace['open'] = lambda path, mode='r': io.StringIO(contents[path]) if mode == 'r' else mock_open()()
        namespace['authenticate_youtube'] = MagicMock()
        return namespace

    def config(self):
        return dict(SMTP_CONFIG, channels=[{
            'channelName': 'Test Channel', 'channelID': 'channel', 'tokenPath': 'token',
            'secretPath': 'secret', 'videoList': 'videos.json',
            'wards': [{'broadcastTitle': 'Sunday Service', 'startTime': '09:00:00', 'streamID': 'stream'}]
        }])

    def test_scheduling_reports_each_step_and_retries_independently(self):
        for failing_step in range(3):
            for failures in (0, 2, 4, 5):
                with self.subTest(step=failing_step, failures=failures):
                    namespace = self.load_functions('schedule.py', self.config())
                    events = []
                    counts = [0, 0, 0]
                    def make_step(index, name):
                        def step(*args):
                            events.append(index)
                            counts[index] += 1
                            if index == failing_step and counts[index] <= failures:
                                raise HttpError('API failure')
                            return [{'id': 'broadcast-id'}, None, 'broadcast-id'][index]
                        step.__name__ = name
                        return step
                    for index, name in enumerate(('schedule_broadcast', 'bind_broadcast_to_stream', 'update_broadcast')):
                        namespace[name] = make_step(index, name)
                    with patch('status_report.send_status_report') as send, redirect_stdout(io.StringIO()):
                        if failures == 5:
                            with self.assertRaises(HttpError):
                                namespace['main']()
                        else:
                            namespace['main']()
                    send.assert_called_once()
                    body = send.call_args.args[2]
                    self.assertIn('Sunday Service', body)
                    self.assertIn('09:00:00', body)
                    self.assertIn('America/Boise', body)
                    if not (failing_step == 0 and failures == 5):
                        self.assertIn('https://www.youtube.com/watch?v=broadcast-id', body)
                    self.assertIn('ISSUES' if failures else 'SUCCESS', send.call_args.args[1])
                    if failures == 5:
                        self.assertIn('ERROR:', body)
                        self.assertNotIn('Scheduling completed', body)
                    else:
                        self.assertIn('Scheduling completed', body)
                    self.assertEqual(events, sorted(events))
                    expected = [1 if i < failing_step else min(failures + 1, 5) if i == failing_step else 0 if failures == 5 else 1 for i in range(3)]
                    self.assertEqual(counts, expected)
                    waits = [call.args[0] for call in namespace['time'].sleep.call_args_list]
                    self.assertEqual(waits, [10] * min(failures, 4) + ([] if failures == 5 else [5]))

    def test_video_outcomes(self):
        for filename, action, eligible, ineligible in (
            ('hide_videos.py', 'update', 'public', 'private'),
            ('remove_videos.py', 'delete', 'private', 'public'),
        ):
            for outcome in ('success', 'skip', 'missing', 'recovered', 'failure'):
                with self.subTest(script=filename, outcome=outcome):
                    namespace = self.load_functions(filename, self.config(), [{'id': 'video-id', 'ward': 'Saved title'}])
                    api = namespace['authenticate_youtube'].return_value.videos.return_value
                    items = [] if outcome == 'missing' else [{'id': 'video-id', 'snippet': {'title': 'Actual video title'}, 'status': {'privacyStatus': ineligible if outcome == 'skip' else eligible}}]
                    # Return fresh dictionaries because hiding mutates the privacy status.
                    api.list.return_value.execute.side_effect = lambda: json.loads(json.dumps({'items': items}))
                    failures = 5 if outcome == 'failure' else 2 if outcome == 'recovered' else 0
                    getattr(api, action).return_value.execute.side_effect = [HttpError('API failure')] * failures + [None]
                    with patch('status_report.send_status_report') as send, redirect_stdout(io.StringIO()):
                        namespace['main']()
                    send.assert_called_once()
                    body = send.call_args.args[2]
                    self.assertIn('Channel: Test Channel', body)
                    self.assertIn('Video ID: video-id', body)
                    self.assertIn('Title: Saved title' if outcome == 'missing' else 'Title: Actual video title', body)
                    self.assertNotIn('https://', body)
                    self.assertTrue(all(c.kwargs['part'] == 'status,snippet' for c in api.list.call_args_list))
                    if filename == 'hide_videos.py' and outcome in ('success', 'recovered', 'failure'):
                        self.assertNotIn('snippet', api.update.call_args.kwargs['body'])
                    self.assertIn({'success': 'SUCCESS:', 'skip': 'SKIPPED:', 'missing': 'WARNING:', 'recovered': 'WARNING:', 'failure': 'ERROR:'}[outcome], body)
                    self.assertIn('ISSUES' if outcome in ('missing', 'recovered', 'failure') else 'SUCCESS', send.call_args.args[1])
                    self.assertEqual(getattr(api, action).return_value.execute.call_count, 0 if outcome in ('skip', 'missing') else min(failures + 1, 5))
                    self.assertEqual([c.args[0] for c in namespace['time'].sleep.call_args_list], [10] * min(failures, 4) + [5])

    def test_authentication_failure_is_reported_in_each_script(self):
        for filename in ('schedule.py', 'hide_videos.py', 'remove_videos.py'):
            with self.subTest(script=filename):
                namespace = self.load_functions(filename, self.config())
                namespace['authenticate_youtube'].side_effect = ValueError('invalid credentials')
                with patch('status_report.send_status_report') as send, redirect_stdout(io.StringIO()):
                    with self.assertRaises(ValueError):
                        namespace['main']()
                send.assert_called_once()
                self.assertIn('invalid credentials', send.call_args.args[2])
                self.assertIn('Test Channel', send.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
