"""Shared SMTP delivery and run reporting for the YouTube scripts."""

import smtplib
import ssl
import sys
from email.message import EmailMessage


def send_status_report(config, subject, body):
    """Send a plain-text report using the top-level smtp configuration."""
    smtp = config['smtp']
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = smtp.get('fromAddress', smtp['username'])
    message['To'] = smtp['destination']
    message.set_content(body)

    use_ssl = smtp.get('useSsl', False)
    port = smtp.get('port', 465 if use_ssl else 587)
    if use_ssl and port == 587:
        raise ValueError(
            'SMTP port 587 uses STARTTLS: set useSsl to false (the connection is still encrypted). '
            'For implicit TLS, set useSsl to true and use your provider\'s implicit TLS port, usually 465.'
        )
    if not use_ssl and port == 465:
        raise ValueError('SMTP port 465 uses implicit TLS: set useSsl to true, or use STARTTLS on port 587.')
    context = ssl.create_default_context()
    connection = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    options = {'timeout': 30}
    if use_ssl:
        options['context'] = context
    with connection(smtp['server'], port, **options) as server:
        if not use_ssl:
            server.starttls(context=context)
        server.login(smtp['username'], smtp['password'])
        server.send_message(message)


class StatusReport:
    """Collect outcomes and email them even when a run exits with an error."""

    def __init__(self, config, script):
        self.config = config
        self.script = script
        self.entries = []
        self.context = 'Starting run'
        self.has_issues = False

    def add(self, status, message):
        self.entries.append(f'{status}: {message}')
        if status in ('WARNING', 'ERROR'):
            self.has_issues = True

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        if error is not None:
            self.add('ERROR', f'{self.context}: {error_type.__name__}: {error}')
            self.add('WARNING', 'Run stopped; remaining operations were not attempted.')
        outcome = 'ISSUES' if self.has_issues else 'SUCCESS'
        body = f'{self.script}: {outcome}\n\n' + '\n'.join(self.entries or ['No operations to perform.'])
        print(body)
        try:
            send_status_report(self.config, f'{self.script}: {outcome}', body)
        except Exception as email_error:
            print(f'Could not send status report: {email_error}', file=sys.stderr)
            if error is None:
                raise
        return False
