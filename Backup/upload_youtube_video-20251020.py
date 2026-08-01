import os
import sys
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime

# Scopes
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtubepartner'  # For Content ID
]
CLIENT_SECRETS_FILE = 'client_secrets.json'
TOKEN_FILE = 'token.json'
DESCRIPTION_FILE = r'D:\Dev\TheTimeThen\VideoAssets\descriptionVideo.txt'

def get_authenticated_service():
    """Authenticate and create a YouTube API service client."""
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Starting authentication...")
    credentials = None

    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'rb') as token:
                credentials = pickle.load(token)
            if credentials and credentials.valid:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Using existing credentials from {TOKEN_FILE}")
            elif credentials and credentials.expired and credentials.refresh_token:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Refreshing expired credentials...")
                credentials.refresh(Request())
                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(credentials, token)
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Credentials refreshed and saved to {TOKEN_FILE}")
            else:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Credentials invalid. Re-authenticating...")
                credentials = None
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error loading credentials from {TOKEN_FILE}: {e}")
            credentials = None
    else:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No credentials found at {TOKEN_FILE}. Starting OAuth flow...")

    if not credentials or not credentials.valid:
        try:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_console()
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(credentials, token)
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authentication complete. Credentials saved to {TOKEN_FILE}")
        except FileNotFoundError:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Fatal Error: {CLIENT_SECRETS_FILE} not found.")
            sys.exit(1)
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authentication error: {e}")
            sys.exit(1)

    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Building YouTube API client...")
    return build('youtube', 'v3', credentials=credentials)

def get_video_description():
    """Read the video description from file."""
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Reading description file {DESCRIPTION_FILE}...")
    try:
        with open(DESCRIPTION_FILE, 'r', encoding='utf-8') as file:
            description = file.read().strip()
            if not description:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Warning: Description file is empty.")
                return "No description provided."
            return description
    except FileNotFoundError:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Warning: Description file not found.")
        return "No description provided."
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error reading description file: {e}")
        return "No description provided."

def create_asset(youtube_partner, video_title):
    """Create a new asset in Content ID."""
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Attempting to create Content ID asset...")
    try:
        asset_body = {
            'metadata': {
                'title': video_title,
                'description': 'Automated asset for uploaded video.'
            },
            'type': 'video'  # Corrected for Content ID API
        }
        response = youtube_partner.assets().insert(
            body=asset_body,
            onBehalfOfContentOwner='contentOwnerId'  # Replace with your actual Content Owner ID
        ).execute()
        asset_id = response['id']
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Created Content ID asset: {asset_id}")
        return asset_id
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Failed to create asset: {e}")
        return None

def claim_video(youtube_partner, video_id, asset_id):
    """Claim the video with the asset and apply monetization policy."""
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Attempting to claim video {video_id}...")
    try:
        claim_body = {
            'videoId': video_id,
            'assetId': asset_id,
            'contentType': 'audiovisual',
            'policy': {
                'rules': [
                    {
                        'action': 'monetize',
                        'conditions': {
                            'matchType': ['reference']
                        }
                    }
                ]
            }
        }
        response = youtube_partner.claims().insert(
            body=claim_body,
            onBehalfOfContentOwner='contentOwnerId'  # Replace with your actual Content Owner ID
        ).execute()
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Created claim with monetization policy on video {video_id}")
        return True
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Failed to claim video: {e}")
        return False

def upload_video(video_path, schedule_date, schedule_time):
    """Upload a video to YouTube and schedule it."""
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Starting upload process for {video_path}...")
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
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Invalid date/time format. Use 'YYYY MM DD' and 'HH:MM'. Error: {e}")
            sys.exit(1)

        # Ensure schedule time is in the future
        current_time = datetime.now()
        if schedule_datetime <= current_time:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Schedule date and time must be in the future.")
            sys.exit(1)

        # Initialize YouTube API client
        youtube = get_authenticated_service()
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authentication successful.")

        # Extract video title
        video_filename = os.path.basename(video_path)
        video_title = os.path.splitext(video_filename)[0].replace('_', ' ').title()

        # Get video description
        video_description = get_video_description()

        # Prepare video metadata
        request_body = {
            'snippet': {
                'title': video_title,
                'description': f"{video_description}\n\n"
                               f"Video uploaded and scheduled via script on {current_time.strftime('%Y-%m-%d %H:%M:%S')}.\n"
                               f"Scheduled for release on {schedule_date} at {schedule_time}.",
                'tags': ['slideshow', 'automated upload', 'python script'],
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
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Starting resumable upload of {video_path}...")
        media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)
        request = youtube.videos().insert(
            part='snippet,status',
            body=request_body,
            media_body=media
        )

        # Execute upload with progress
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                sys.stdout.write(f"\r{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Upload progress: {progress}%")
                sys.stdout.flush()

        video_id = response['id']
        print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Video uploaded successfully! Video ID: {video_id}")
        print(f"Title: {response['snippet']['title']}")
        print(f"Scheduled for release on {schedule_date} at {schedule_time} (Privacy: Private).")
        print(f"View it at: https://youtu.be/{video_id}")

        # Attempt Content ID monetization
        try:
            youtube_partner = build('youtubePartner', 'v1', credentials=youtube.credentials)
            asset_id = create_asset(youtube_partner, video_title)
            if asset_id:
                success = claim_video(youtube_partner, video_id, asset_id)
                if success:
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Monetization enabled via Content ID.")
                else:
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Content ID claim failed. Configure monetization in YouTube Studio.")
            else:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Asset creation failed. Configure monetization in YouTube Studio.")
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Content ID error (check access): {e}. Configure monetization in YouTube Studio.")

    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Fatal error during upload: {e}")
        sys.exit(1)

if __name__ == '__main__':
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Script started with arguments: {sys.argv}")
    if len(sys.argv) != 4:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Usage: python upload_youtube_video.py <video_path> <schedule_date> <schedule_time>")
        print(f"Example: python upload_youtube_video.py 'D:\\Videos\\my_new_video.mp4' '2025 11 20' '14:00'")
        sys.exit(1)

    video_path = sys.argv[1]
    schedule_date = sys.argv[2]
    schedule_time = sys.argv[3]
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Running with video_path={video_path}, schedule_date={schedule_date}, schedule_time={schedule_time}")
    upload_video(video_path, schedule_date, schedule_time)