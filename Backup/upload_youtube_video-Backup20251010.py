import os
import sys
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime

# Scopes required for YouTube Data API
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secrets.json'
TOKEN_FILE = 'token.json'
REDIRECT_PORT = 60515

def get_authenticated_service():
    """Authenticate and create a YouTube API service client using stored or new credentials."""
    credentials = None

    # Load credentials from file if it exists
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'rb') as token:
                credentials = pickle.load(token)
            # Check if credentials are valid or can be refreshed
            if credentials and credentials.valid:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Using existing credentials from {TOKEN_FILE}")
            elif credentials and credentials.expired and credentials.refresh_token:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Refreshing expired credentials...")
                credentials.refresh(Request())
                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(credentials, token)
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Credentials refreshed and saved to {TOKEN_FILE}")
            else:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Invalid credentials in {TOKEN_FILE}. Re-authentication required.")
                credentials = None
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error loading credentials from {TOKEN_FILE}: {e}")
            credentials = None
    else:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No credentials found at {TOKEN_FILE}. One-time browser authentication required.")

    # If no valid credentials, perform OAuth flow
    if not credentials or not credentials.valid:
        try:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Initiating OAuth flow (one-time setup)...")
            print("Please complete browser authentication to generate credentials. This is required only once.")
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                SCOPES,
                redirect_uri=f'http://localhost:{REDIRECT_PORT}/'
            )
            credentials = flow.run_local_server(
                port=REDIRECT_PORT,
                open_browser=True,
                timeout_seconds=300
            )
            # Save credentials for future use
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(credentials, token)
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Credentials saved to {TOKEN_FILE}. Future runs will be automated.")
        except FileNotFoundError:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: {CLIENT_SECRETS_FILE} not found. Download it from Google Cloud Console.")
            sys.exit(1)
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authentication error: {e}")
            sys.exit(1)

    return build('youtube', 'v3', credentials=credentials)

def upload_video(video_path, schedule_date, schedule_time):
    """Upload a video to YouTube and schedule it for the specified date and time."""
    try:
        # Validate video file
        if not os.path.exists(video_path):
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Video file not found at {video_path}")
            sys.exit(1)

        # Parse and validate schedule date and time
        try:
            schedule_datetime = datetime.strptime(f"{schedule_date} {schedule_time}", "%Y %m %d %H:%M")
            schedule_iso = schedule_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Invalid date or time format. Use 'YYYY MM DD' and 'HH:MM'. Error: {e}")
            sys.exit(1)

        # Ensure the schedule time is in the future
        current_time = datetime.now()
        if schedule_datetime <= current_time:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Schedule date and time must be in the future.")
            sys.exit(1)

        # Initialize YouTube API client
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authenticating with YouTube API...")
        youtube = get_authenticated_service()
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authentication successful.")

        # Extract video title from filename
        video_filename = os.path.basename(video_path)
        video_title = os.path.splitext(video_filename)[0].replace('_', ' ').title()

        # Prepare video metadata
        request_body = {
            'snippet': {
                'title': video_title,
                'description': f'Video uploaded and scheduled via script on {current_time.strftime("%Y-%m-%d %H:%M:%S")}.\n'
                              f'Scheduled for release on {schedule_date} at {schedule_time}.',
                'tags': ['slideshow', 'automated upload'],
                'categoryId': '22',  # People & Blogs
                'defaultLanguage': 'en',
                'defaultAudioLanguage': 'en'
            },
            'status': {
                'privacyStatus': 'private',
                'publishAt': schedule_iso,
                'selfDeclaredMadeForKids': False
            }
        }

        # Upload the video
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Starting upload of {video_path}...")
        media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)  # 1MB chunks
        request = youtube.videos().insert(
            part='snippet,status',
            body=request_body,
            media_body=media
        )

        # Execute the upload with progress feedback
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Uploaded {progress}%")

        video_id = response['id']
        print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Video uploaded successfully! Video ID: {video_id}")
        print(f"Scheduled for release on {schedule_date} at {schedule_time}.")
        print(f"View it at: https://youtu.be/{video_id}")

    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error uploading video: {e}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Usage: python upload_youtube_video.py <video_path> <schedule_date> <schedule_time>")
        print(f"Example: python upload_youtube_video.py 'D:\\Youtube\\TTT\\20251010\\20251010_slideshow.mp4' '2025 11 20' '14:00'")
        sys.exit(1)

    video_path = sys.argv[1]
    schedule_date = sys.argv[2]
    schedule_time = sys.argv[3]

    upload_video(video_path, schedule_date, schedule_time)