import os
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]

def authenticate_youtube():
    creds = None
    if os.path.exists("token-48.json"):
        creds = Credentials.from_authorized_user_file("token-48.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("secrets-48.json", SCOPES)
            creds = flow.run_local_server(port=8080)
        with open("token-48.json", "w") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def list_live_streams(youtube):
    request = youtube.liveStreams().list(
        part="id,snippet,cdn",
        mine=True,
        #id="UCQaojnFn9qry524kxRRnkHw",
        maxResults=50
    )
    response = request.execute()

    streams = response.get("items", [])
    if not streams:
        print("No live streams found.")
        return

    print(f"{'Title':<30} {'Stream ID':<35} {'Ingestion URL':<45} {'Stream Key'}")
    print("-" * 130)
    for stream in streams:
        title = stream['snippet']['title']
        stream_id = stream['id']
        ingestion_info = stream['cdn'].get('ingestionInfo', {})
        ingestion_url = ingestion_info.get('ingestionAddress', 'N/A')
        stream_key = ingestion_info.get('streamName', 'N/A')

        print(f"{title:<30} {stream_id:<35} {ingestion_url:<45} {stream_key}")

if __name__ == "__main__":
    youtube = authenticate_youtube()
    list_live_streams(youtube)
