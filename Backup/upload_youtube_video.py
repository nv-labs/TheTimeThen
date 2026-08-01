import os
import sys
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime

# Scopes required for YouTube Data API to upload videos
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secrets.json'
TOKEN_FILE = 'token.json'

def get_authenticated_service():
    """Authenticate and create a YouTube API service client using stored or new credentials."""
    credentials = None

    # --- 1. Load existing or refresh credentials ---
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
                # If credentials exist but are invalid and cannot be refreshed, we need to re-authenticate
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Credentials are invalid/unrefreshable. Re-authentication required.")
                credentials = None
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error loading credentials from {TOKEN_FILE}: {e}")
            credentials = None
    else:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No credentials found at {TOKEN_FILE}. One-time authentication required.")

    # --- 2. Perform one-time manual console OAuth flow if no valid credentials ---
    if not credentials or not credentials.valid:
        try:
            print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Starting ONE-TIME console OAuth flow...")
            print("Action required: You will need to open a URL in your browser and paste a code back here.")
            
            # Initialize flow using the installed application secrets file
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                SCOPES
            )
            
            # Use run_console() instead of run_local_server()
            # This prints the URL to the console, and prompts the user to paste the verification code back.
            credentials = flow.run_console()
            
            # Save credentials for future, non-interactive use
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(credentials, token)
            print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authentication complete. Credentials saved to {TOKEN_FILE}.")
            print("Future runs will use the saved token and will not require browser interaction.")

        except FileNotFoundError:
            print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Fatal Error: {CLIENT_SECRETS_FILE} not found.")
            print("Please download your client secrets JSON file from Google Cloud Console and ensure it's in the script's directory.")
            sys.exit(1)
        except Exception as e:
            print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authentication error: {e}")
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
            # Assumes schedule_date is 'YYYY MM DD' and schedule_time is 'HH:MM'
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

        # Initialize YouTube API client (handles auth/refresh)
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
                'tags': ['slideshow', 'automated upload', 'python script'],
                'categoryId': '22',  # People & Blogs
                'defaultLanguage': 'en',
                'defaultAudioLanguage': 'en'
            },
            'status': {
                'privacyStatus': 'private', # Use 'public' for immediate publishing
                'publishAt': schedule_iso,
                'selfDeclaredMadeForKids': False
            }
        }

        # Upload the video
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Starting resumable upload of {video_path}...")
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
                # Print progress to console, overwriting the previous line
                sys.stdout.write(f"\r{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Upload progress: {progress}%")
                sys.stdout.flush()

        video_id = response['id']
        print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Video uploaded successfully! Video ID: {video_id}")
        print(f"Title: {response['snippet']['title']}")
        print(f"Scheduled for release on {schedule_date} at {schedule_time} (Privacy: Private).")
        print(f"View it at: https://youtu.be/{video_id}")

    except Exception as e:
        print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: A fatal error occurred during upload: {e}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Usage: python youtube_uploader.py <video_path> <schedule_date> <schedule_time>")
        print(f"Example: python youtube_uploader.py 'D:\\Videos\\my_new_video.mp4' '2025 11 20' '14:00'")
        print(f"Note: Schedule date must be 'YYYY MM DD' and time must be 'HH:MM'.")
        sys.exit(1)

    video_path = sys.argv[1]
    schedule_date = sys.argv[2]
    schedule_time = sys.argv[3]

    upload_video(video_path, schedule_date, schedule_time)
