import argparse
import json

from list_streams import authenticate_youtube


def list_videos(youtube):
    response = youtube.channels().list(part="contentDetails", mine=True).execute()
    channels = response.get("items", [])
    if not channels:
        print("No channel found for these credentials.")
        return

    uploads_id = channels[0]['contentDetails']['relatedPlaylists']['uploads']
    page_token = None
    found_videos = False

    while True:
        response = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_id,
            maxResults=50,
            pageToken=page_token
        ).execute()

        for video in response.get("items", []):
            if not found_videos:
                print(f"{'Title':<60} {'Video ID':<15} {'Published':<22} URL")
                print("-" * 145)
                found_videos = True

            title = video['snippet']['title']
            video_id = video['contentDetails']['videoId']
            published = video['contentDetails'].get('videoPublishedAt', 'N/A')
            print(f"{title:<60} {video_id:<15} {published:<22} https://www.youtube.com/watch?v={video_id}")

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    if not found_videos:
        print("No videos found.")


def parse_args():
    parser = argparse.ArgumentParser(description="Lists YouTube videos from a given config file")
    parser.add_argument("--config", required=True, help="Full path to the config file")
    return parser.parse_args()


def main():
    args = parse_args()

    with open(args.config) as c:
        config = json.load(c)

    for channel in config['channels']:
        print(f"Listing videos for channel: {channel['channelName']}")
        youtube = authenticate_youtube(channel['tokenPath'], channel['secretPath'])
        list_videos(youtube)


if __name__ == "__main__":
    main()
