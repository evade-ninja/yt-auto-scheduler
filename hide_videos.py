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

    for channel in config['channels']:
        print(f"Setting videos as private for channel: {channel['channelName']}")
        youtube = authenticate_youtube(channel['tokenPath'], channel['secretPath'])

        #Read in the videos from the videoList
        video_list = []

        with open(channel['videoList']) as v_file:
            video_list = json.load(v_file)
        
        for video in video_list:
            print(f"\tHiding {video['id']}")

            attempt = 0
            success = False

            while attempt < 5 and not success:
                attempt += 1
                print(f"\t\tAttempt {attempt}/5")

                try:
                    request = youtube.videos().list(part="status", id=video['id'])
                    response = request.execute()

                    #Only make the video private if it is public
                    if len(response['items']) > 0:
                        if response['items'][0]['status']['privacyStatus'] == 'public':
                            newBody = response['items'][0]
                            newBody['status']['privacyStatus'] = 'private'

                            request = youtube.videos().update(
                                part = "status",
                                body = newBody
                            )
                            response = request.execute()
                    else:
                        print("Couldn't find video with ID:" + video['id'])
                    success = True
                except HttpError as error:
                    print(f"\t\tError hiding {video['id']}: {error}")
                    if attempt < 5:
                        time.sleep(10)
                    else:
                        print(f"\t\tGiving up on {video['id']} after 5 attempts.")

            #wait a little bit
            time.sleep(5)

if __name__ == "__main__":
    main()
