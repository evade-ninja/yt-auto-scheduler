import os
import json
import argparse
import datetime
import pytz
from datetime import datetime, timedelta
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

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

def schedule_broadcast(youtube, channel_id, title, description, start_time):
    request = youtube.liveBroadcasts().insert(
        part="snippet,contentDetails,status",
        body={
            "snippet": {
                "channelId": channel_id,
                "title": title,
                "description": description,
                "scheduledStartTime": start_time.isoformat("T"),
                "categoryId": 22
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": True
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,
                "enableDvr": False,
                "enableClosedCaptions": False,
                "enableContentEncryption": False,
                "enableEmbed": False,
                "setRecordFromStart": True
            }
        }
    )
    return request.execute()

def update_broadcast(youtube, oldBody, start_time):

    request = youtube.videos().list(part="snippet", id=oldBody['id'])
    response = request.execute()

    newBody = response['items'][0]
    newBody['snippet']['categoryId'] = "22"
    newBody['snippet']['scheduledStartTime'] = start_time.isoformat("T")

    request = youtube.videos().update(
        part="snippet",
        body=newBody
    )
    response = request.execute()
    return newBody['id']

def bind_broadcast_to_stream(youtube, broadcast_id, stream_id):
    request = youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id
    )
    return request.execute()


def parse_args():
    parser = argparse.ArgumentParser(description="Schedules YouTube Streams from a given config file")
    parser.add_argument("--config", required=True, help="Full path to the config file")
    return parser.parse_args()

def parse_args_old():
    parser = argparse.ArgumentParser(description="Schedule a YouTube stream with an existing stream ID.")
    parser.add_argument("--channel_id", required=True, help="YouTube channel ID")
    parser.add_argument("--stream_id", required=True, help="YouTube Live Stream ID to bind")
    parser.add_argument("--title", required=True, help="Title of the broadcast")
    parser.add_argument("--description", default="", help="Description of the broadcast")
    parser.add_argument("--time", required=True, help="Scheduled start time in ISO UTC format (e.g., 2025-07-14T18:00:00)")
    return parser.parse_args()

def main():
    #Load config file
    args = parse_args()

    with open(args.config) as c:
        config = json.load(c)

    #Calculate next sunday
    today = datetime.now(pytz.timezone("America/Boise"))
    days_until_sunday = (6 - today.weekday()) % 7

    if days_until_sunday == 0:  # If today is Sunday, move to the next Sunday
        days_until_sunday = 7

    # Calculate the next Sunday's date
    next_sunday = today + timedelta(days=days_until_sunday)
    next_sunday = next_sunday.strftime('%Y-%m-%d')

    for channel in config['channels']:
        print(f"Scheduling for channel: {channel['channelName']}")
        youtube = authenticate_youtube(channel['tokenPath'], channel['secretPath'])
        videos = []
        for ward in channel['wards']:
            start_time = datetime.fromisoformat(f"{next_sunday}T{ward['startTime']}").astimezone(pytz.utc)
            start_time = start_time.replace(tzinfo=None)
            print(f"\tScheduling {ward['broadcastTitle']} for {start_time.isoformat()}")
            broadcast = schedule_broadcast(youtube, channel['channelID'], ward['broadcastTitle'], "", start_time)
            bind_broadcast_to_stream(youtube, broadcast["id"], ward['streamID'])
            video_id = update_broadcast(youtube, broadcast, start_time)

            #record the video_id so that we can remove the videos later
            videos.append({
                "id": video_id,
                "startTime": ward['startTime']
            })


if __name__ == "__main__":
    main()
