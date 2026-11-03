import os
import json
import time
import argparse
import datetime
import pytz
from datetime import datetime, timedelta
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from status_report import StatusReport

# Required scope for scheduling and binding broadcasts
SCOPES = ["https://www.googleapis.com/auth/youtube"]

def authenticate_youtube(tokenPath, secretPath):
    creds = None
    if os.path.exists(tokenPath):
        creds = Credentials.from_authorized_user_file(tokenPath, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secretPath, SCOPES)
            creds = flow.run_local_server(port=8080)

        with open(tokenPath, "w") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def parse_args():
    parser = argparse.ArgumentParser(description="Sets YouTube Videos as private from a given config file")
    parser.add_argument("--config", required=True, help="Full path to the config file")
    return parser.parse_args()

def main():
    #Load config file
    args = parse_args()

    with open(args.config) as c:
        config = json.load(c)

    with StatusReport(config, "hide_videos.py") as report:
        for channel in config['channels']:
            print(f"Setting videos as private for channel: {channel['channelName']}")
            report.context = f"Channel: {channel['channelName']}"
            youtube = authenticate_youtube(channel['tokenPath'], channel['secretPath'])

            #Read in the videos from the videoList
            video_list = []

            with open(channel['videoList']) as v_file:
                video_list = json.load(v_file)

            for video in video_list:
                title = video.get('title') or video.get('ward') or 'Unavailable'
                report.context = f"Channel: {channel['channelName']} | Title: {title} | Video ID: {video['id']}"
                print(f"\tHiding {video['id']}")

                attempt = 0
                success = False

                while attempt < 5 and not success:
                    attempt += 1
                    print(f"\t\tAttempt {attempt}/5")

                    try:
                        request = youtube.videos().list(part="status,snippet", id=video['id'])
                        response = request.execute()
                        if response['items']:
                            title = response['items'][0].get('snippet', {}).get('title') or title
                            report.context = f"Channel: {channel['channelName']} | Title: {title} | Video ID: {video['id']}"

                        #Only make the video private if it is public
                        if len(response['items']) > 0:
                            if response['items'][0]['status']['privacyStatus'] == 'public':
                                newBody = {
                                    'id': response['items'][0]['id'],
                                    'status': response['items'][0]['status']
                                }
                                newBody['status']['privacyStatus'] = 'private'

                                request = youtube.videos().update(
                                    part = "status",
                                    body = newBody
                                )
                                response = request.execute()
                                report.add('SUCCESS', f'{report.context} | Video made private')
                            else:
                                report.add('SKIPPED', f"{report.context} | Privacy is {response['items'][0]['status']['privacyStatus']}; no change")
                        else:
                            print("Couldn't find video with ID:" + video['id'])
                            report.add('WARNING', f'{report.context} | Video not found')
                        success = True
                    except HttpError as error:
                        print(f"\t\tError hiding {video['id']}: {error}")
                        if attempt < 5:
                            report.add('WARNING', f'{report.context} | Attempt {attempt}/5 failed: {error}; retrying')
                            time.sleep(10)
                        else:
                            report.add('ERROR', f'{report.context} | Failed to hide video after 5 attempts: {error}')
                            print(f"\t\tGiving up on {video['id']} after 5 attempts.")

                #wait a little bit
                time.sleep(5)


if __name__ == "__main__":
    main()
