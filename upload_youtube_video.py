import os
import sys
import pickle
import json
import re
import random
import subprocess
import time
from urllib import request, error
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime, timezone

# Scopes
SCOPES = [
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.force-ssl'
]
CLIENT_SECRETS_FILE = 'client_secrets.json'
TOKEN_FILE = 'token.json'
DESCRIPTION_FILE = r'D:\Dev\TheTimeThen\VideoAssets\descriptionVideo.txt'
USED_TITLES_FILE = r'D:\Dev\TheTimeThen\VideoAssets\Names Youtube Already Used.md'
ENABLE_END_SCREEN_AUTOMATION = os.environ.get('YT_AUTO_IMPORT_END_SCREEN', '1') == '1'
PLAYWRIGHT_STUDIO_PROFILE_DIR = os.environ.get(
    'YT_PLAYWRIGHT_PROFILE_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '.yt_studio_profile')
)
STUDIO_REMOTE_DEBUG_PORT = int(os.environ.get('YT_STUDIO_REMOTE_DEBUG_PORT', '9222'))
TITLE_MODEL = os.environ.get('YT_TITLE_MODEL', 'gpt-4.1-mini')
PLAYLIST_TITLE_PREFIX = os.environ.get('YT_PLAYLIST_TITLE_PREFIX', 'Historical Old Photos')


def ensure_playwright_available():
    """Ensure the Playwright Python package is installed for the current interpreter."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Playwright not found for {sys.executable}. Installing...")

    try:
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'playwright'],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        from playwright.sync_api import sync_playwright  # noqa: F401
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Playwright package setup complete.")
        return True
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Failed to install Playwright automatically: {e}")
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Interpreter in use: {sys.executable}")
        return False

def has_required_scopes(credentials):
    """Return True when the cached token includes all required OAuth scopes."""
    granted_scopes = set(credentials.granted_scopes or credentials.scopes or [])
    return set(SCOPES).issubset(granted_scopes)

def get_authenticated_service():
    """Authenticate and create a YouTube API service client."""
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Starting authentication...")
    credentials = None

    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'rb') as token:
                credentials = pickle.load(token)
            if credentials and credentials.valid and has_required_scopes(credentials):
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Using existing credentials from {TOKEN_FILE}")
            elif credentials and credentials.expired and credentials.refresh_token:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Refreshing expired credentials...")
                credentials.refresh(Request())
                if has_required_scopes(credentials):
                    with open(TOKEN_FILE, 'wb') as token:
                        pickle.dump(credentials, token)
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Credentials refreshed and saved to {TOKEN_FILE}")
                else:
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Cached credentials are missing one or more required scopes. Re-authenticating...")
                    credentials = None
            else:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Credentials invalid. Re-authenticating...")
                credentials = None
            if credentials and not has_required_scopes(credentials):
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Cached credentials are missing one or more required scopes. Re-authenticating...")
                credentials = None
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error loading credentials from {TOKEN_FILE}: {e}")
            credentials = None
    else:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No credentials found at {TOKEN_FILE}. Starting OAuth flow...")

    if not credentials or not credentials.valid:
        try:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
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
    return build('youtube', 'v3', credentials=credentials), credentials

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


def _normalize_title(title):
    """Normalize a title for duplicate checking."""
    normalized = re.sub(r'\s+', ' ', (title or '').strip().lower())
    return normalized.strip('"\'`')


def _clean_title(title):
    """Ensure title is short and upload-friendly."""
    cleaned = re.sub(r'\s+', ' ', (title or '').replace('\n', ' ').replace('\r', ' ')).strip()
    cleaned = re.sub(r'^[\-\*\d\.)\s]+', '', cleaned)
    cleaned = cleaned.strip('"\'` ')
    if not cleaned:
        return ''

    words = cleaned.split()
    if len(words) > 8:
        cleaned = ' '.join(words[:8])
    if len(cleaned) > 62:
        cleaned = cleaned[:62].rstrip(' :;,.!-')
    return cleaned


def _load_used_titles(file_path=USED_TITLES_FILE):
    """Return a set of normalized used titles from disk."""
    used = set()
    if not os.path.exists(file_path):
        return used

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                value = _clean_title(line)
                if value:
                    used.add(_normalize_title(value))
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Warning: could not read used titles file: {e}")
    return used


def _append_used_title(title, file_path=USED_TITLES_FILE):
    """Persist a newly used title to prevent duplicates next runs."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f"{title}\n")
        return True
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Warning: could not append title to used list: {e}")
        return False


def _parse_title_candidates(text):
    """Extract title candidates from model output text."""
    candidates = []
    for line in (text or '').splitlines():
        cleaned = _clean_title(line)
        if cleaned:
            candidates.append(cleaned)
    return candidates


def _generate_ai_title_candidates(used_titles, count=12):
    """Generate short viral title candidates using OpenAI Responses API."""
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: OPENAI_API_KEY not set. Using local fallback title generator.")
        return []

    prompt = (
        "Generate {count} unique YouTube titles for old historical photo videos. "
        "Rules: short, catchy, viral style, 3-8 words, no emoji, no hashtags, one title per line. "
        "Avoid these existing titles:\n{used_titles}"
    ).format(count=count, used_titles='\n'.join(sorted(list(used_titles))[:250]))

    payload = {
        'model': TITLE_MODEL,
        'temperature': 0.9,
        'input': [
            {
                'role': 'system',
                'content': (
                    'You write high-CTR YouTube titles for historical photo compilations. '
                    'Titles must stay concise and readable.'
                )
            },
            {
                'role': 'user',
                'content': prompt
            }
        ]
    }

    req = request.Request(
        'https://api.openai.com/v1/responses',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        },
        method='POST'
    )

    try:
        with request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            output_text = data.get('output_text', '')
            if not output_text:
                fragments = []
                for item in data.get('output', []):
                    for content in item.get('content', []):
                        text = content.get('text')
                        if text:
                            fragments.append(text)
                output_text = '\n'.join(fragments)
            return _parse_title_candidates(output_text)
    except error.HTTPError as e:
        try:
            details = e.read().decode('utf-8')
        except Exception:
            details = str(e)
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: AI title generation HTTP error: {details}")
        return []
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: AI title generation failed: {e}")
        return []


def _generate_local_title_candidates(count=30):
    """Fallback title candidates when AI is unavailable."""
    a = [
        'Forgotten', 'Hidden', 'Lost', 'Untold', 'Rare', 'Raw', 'Unseen', 'Faded', 'Secret', 'Old'
    ]
    b = [
        'History', 'Photos', 'Moments', 'Past', 'Archives', 'Memories', 'Frames', 'Scenes', 'Stories', 'Snapshots'
    ]
    c = [
        'Revealed', 'Uncovered', 'That Still Matter', 'You Never Saw', 'From Another Time',
        'That Feel Alive', 'Before It Changed', 'In One Frame', 'Caught on Film', 'Up Close'
    ]
    candidates = []
    for _ in range(count):
        style = random.randint(1, 3)
        if style == 1:
            candidates.append(f"{random.choice(a)} {random.choice(b)}")
        elif style == 2:
            candidates.append(f"{random.choice(a)} {random.choice(b)} {random.choice(c)}")
        else:
            candidates.append(f"{random.choice(b)} {random.choice(c)}")
    return candidates


def choose_unique_video_title(video_path, used_titles_file=USED_TITLES_FILE):
    """Choose a short unique title, append it to used-title file, and return it."""
    used_titles = _load_used_titles(used_titles_file)
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Loaded {len(used_titles)} existing used titles.")

    ai_candidates = _generate_ai_title_candidates(used_titles, count=14)
    fallback_candidates = _generate_local_title_candidates(count=50)
    all_candidates = ai_candidates + fallback_candidates

    for candidate in all_candidates:
        cleaned = _clean_title(candidate)
        normalized = _normalize_title(cleaned)
        if not cleaned:
            continue
        if normalized in used_titles:
            continue
        _append_used_title(cleaned, used_titles_file)
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Selected unique video title: {cleaned}")
        return cleaned

    # Last-resort fallback to filename if everything collides.
    filename_title = _clean_title(os.path.splitext(os.path.basename(video_path))[0].replace('_', ' '))
    if not filename_title:
        filename_title = f"Rare History Photos {datetime.now().strftime('%Y%m%d%H%M%S')}"
    normalized = _normalize_title(filename_title)
    if normalized in used_titles:
        filename_title = f"{filename_title} {datetime.now().strftime('%H%M')}"
    _append_used_title(filename_title, used_titles_file)
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Fallback video title used: {filename_title}")
    return filename_title



def _studio_manual_fallback(studio_url):
    """Return a manual-fallback signal without opening a browser."""
    return False


def _click_first_visible(page, selectors, timeout_ms=6000):
    """Click the first matching visible selector and return True on success."""
    for selector in selectors:
        try:
            page.locator(selector).first.wait_for(state='visible', timeout=timeout_ms)
            page.locator(selector).first.click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def _find_supported_studio_browser():
    """Return the first installed Edge/Chrome executable suitable for YouTube Studio sign-in."""
    configured_path = os.environ.get('YT_STUDIO_BROWSER_PATH')
    if configured_path and os.path.exists(configured_path):
        return configured_path

    local_app_data = os.environ.get('LOCALAPPDATA', '')
    program_files = os.environ.get('PROGRAMFILES', '')
    program_files_x86 = os.environ.get('PROGRAMFILES(X86)', '')
    candidates = [
        os.path.join(local_app_data, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(program_files, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(program_files_x86, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(local_app_data, 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(program_files, 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(program_files_x86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _connect_to_studio_browser(playwright, timeout_seconds=30):
    """Connect to an Edge/Chrome instance exposed over CDP on localhost."""
    endpoint = f'http://127.0.0.1:{STUDIO_REMOTE_DEBUG_PORT}'
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            return playwright.chromium.connect_over_cdp(endpoint)
        except Exception as e:
            last_error = e
            time.sleep(1)
    if last_error:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Could not connect to browser debug endpoint {endpoint}: {last_error}")
    return None


def _launch_studio_browser_for_automation(studio_url, playwright):
    """Launch a real local browser with remote debugging enabled and connect to it."""
    existing_browser = _connect_to_studio_browser(playwright, timeout_seconds=2)
    if existing_browser:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Connected to existing browser on debug port {STUDIO_REMOTE_DEBUG_PORT}.")
        return existing_browser, False

    browser_path = _find_supported_studio_browser()
    if not browser_path:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No supported Edge/Chrome installation found for Studio automation.")
        return None, False

    os.makedirs(PLAYWRIGHT_STUDIO_PROFILE_DIR, exist_ok=True)
    subprocess.Popen(
        [
            browser_path,
            f'--remote-debugging-port={STUDIO_REMOTE_DEBUG_PORT}',
            f'--user-data-dir={PLAYWRIGHT_STUDIO_PROFILE_DIR}',
            '--no-first-run',
            '--no-default-browser-check',
            'https://studio.youtube.com/'
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    browser = _connect_to_studio_browser(playwright, timeout_seconds=30)
    if browser:
        return browser, True

    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Browser launched but Playwright could not attach over CDP.")
    return None, False


def _studio_sign_in_blocked(page):
    """Return True when Google shows the secure-browser block page."""
    blocking_text = [
        'This browser or app may not be secure',
        'Try using a different browser'
    ]
    for text in blocking_text:
        try:
            if page.get_by_text(text, exact=False).first.is_visible(timeout=1500):
                return True
        except Exception:
            continue
    return False


def _wait_for_studio_sign_in(page, studio_url, timeout_seconds=180):
    """Wait for the Studio sign-in flow to finish, failing fast on Google browser blocks."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _studio_sign_in_blocked(page):
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Google blocked sign-in in the automated browser window.")
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Use your regular Edge/Chrome window to complete Studio steps instead.")
            return False
        if 'studio.youtube.com' in page.url:
            page.goto(studio_url, wait_until='domcontentloaded', timeout=120000)
            page.wait_for_timeout(3000)
            return True
        page.wait_for_timeout(1000)

    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Sign-in not completed in time.")
    return False


def _find_or_open_studio_editor_page(context, studio_url, video_id):
    """Select a page already on the target video editor, or open a new one."""
    target_fragment = f"/video/{video_id}/editor"

    for page in context.pages:
        try:
            if 'studio.youtube.com' in page.url and target_fragment in page.url:
                page.bring_to_front()
                return page
        except Exception:
            continue

    for page in context.pages:
        try:
            if 'studio.youtube.com' in page.url:
                page.bring_to_front()
                page.goto(studio_url, wait_until='domcontentloaded', timeout=120000)
                return page
        except Exception:
            continue

    page = context.new_page()
    page.goto(studio_url, wait_until='domcontentloaded', timeout=120000)
    return page


def add_end_screen_from_latest(video_id):
    """Import end screen from latest video in YouTube Studio (automated when possible)."""
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Adding end screen from latest video for {video_id}...")
    studio_url = f"https://studio.youtube.com/video/{video_id}/editor"

    if not ENABLE_END_SCREEN_AUTOMATION:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: End screen automation disabled (set YT_AUTO_IMPORT_END_SCREEN=1 to enable).")
        return _studio_manual_fallback(studio_url)

    if not ensure_playwright_available():
        return _studio_manual_fallback(studio_url)

    from playwright.sync_api import sync_playwright

    browser = None
    launched_browser = False
    try:
        with sync_playwright() as p:
            browser, launched_browser = _launch_studio_browser_for_automation(studio_url, p)
            if not browser:
                return _studio_manual_fallback(studio_url)

            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = _find_or_open_studio_editor_page(context, studio_url, video_id)
            page.wait_for_timeout(4000)

            if 'accounts.google.com' in page.url:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: First-time setup: sign in to YouTube Studio in the opened browser window.")
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Waiting up to 3 minutes for Studio sign-in to complete...")
                if not _wait_for_studio_sign_in(page, studio_url):
                    return _studio_manual_fallback(studio_url)

            end_screen_clicked = _click_first_visible(page, [
                "button:has-text('End screen and cards')",
                "button:has-text('End screen')",
                "ytcp-button:has-text('End screen and cards')",
                "ytcp-button:has-text('End screen')",
                "[aria-label*='End screen']",
                "[aria-label*='end screen']",
                "[title*='End screen']",
            ])

            if not end_screen_clicked:
                _click_first_visible(page, [
                    "a:has-text('Editor')",
                    "tp-yt-paper-tab:has-text('Editor')",
                    "[role='tab']:has-text('Editor')",
                ], timeout_ms=4000)
                page.wait_for_timeout(1500)
                end_screen_clicked = _click_first_visible(page, [
                    "button:has-text('End screen and cards')",
                    "button:has-text('End screen')",
                    "ytcp-button:has-text('End screen and cards')",
                    "ytcp-button:has-text('End screen')",
                    "[aria-label*='End screen']",
                    "[aria-label*='end screen']",
                    "[title*='End screen']",
                ], timeout_ms=10000)

            if not end_screen_clicked:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Could not locate End screen button in Studio.")
                return _studio_manual_fallback(studio_url)

            page.wait_for_timeout(1500)

            import_clicked = _click_first_visible(page, [
                "button:has-text('Import from latest video')",
                "ytcp-button:has-text('Import from latest video')",
                "button:has-text('Import from video')",
                "ytcp-button:has-text('Import from video')",
                "button:has-text('Import')",
                "ytcp-button:has-text('Import')",
            ], timeout_ms=8000)
            if not import_clicked:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Could not locate Import button in End screen panel.")
                return _studio_manual_fallback(studio_url)

            page.wait_for_timeout(2500)

            # If a picker appears, choose first available template/video entry.
            _click_first_visible(page, [
                "tp-yt-paper-item",
                "ytcp-entity-card",
                "[role='option']",
            ], timeout_ms=2000)

            save_clicked = _click_first_visible(page, [
                "button:has-text('Save')",
                "ytcp-button:has-text('Save')",
                "[aria-label='Save']",
            ], timeout_ms=10000)

            if save_clicked:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: End screen imported from latest video and saved.")
                return True

            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Could not click Save automatically.")
            return _studio_manual_fallback(studio_url)
    except Exception as e:
        return _studio_manual_fallback(studio_url)
    finally:
        if browser and launched_browser:
            try:
                browser.close()
            except Exception:
                pass


def add_video_to_playlist(youtube, video_id):
    """Find the playlist that starts with PLAYLIST_TITLE_PREFIX and add the video to it."""
    print(
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: "
        f"Searching for playlist starting with '{PLAYLIST_TITLE_PREFIX}'..."
    )
    try:
        playlists = []
        next_page = None
        while True:
            response = youtube.playlists().list(
                part='snippet',
                mine=True,
                maxResults=50,
                pageToken=next_page
            ).execute()
            playlists.extend(response.get('items', []))
            next_page = response.get('nextPageToken')
            if not next_page:
                break

        playlist_id = None
        for pl in playlists:
            title = pl['snippet']['title'].strip()
            if title.lower().startswith(PLAYLIST_TITLE_PREFIX.lower()):
                playlist_id = pl['id']
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Found playlist: {title} ({playlist_id})")
                break

        if not playlist_id:
            print(
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: "
                f"No playlist starting with '{PLAYLIST_TITLE_PREFIX}' found."
            )
            return False

        youtube.playlistItems().insert(
            part='snippet',
            body={
                'snippet': {
                    'playlistId': playlist_id,
                    'resourceId': {
                        'kind': 'youtube#video',
                        'videoId': video_id
                    }
                }
            }
        ).execute()
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Video {video_id} added to playlist {playlist_id}.")
        return True
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Failed to add video to playlist: {e}")
        return False


def upload_video_thumbnail(youtube, video_id, thumbnail_path):
    """Upload or update the custom thumbnail for the given YouTube video."""
    if not os.path.exists(thumbnail_path):
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Thumbnail file not found: {thumbnail_path}")
        return False

    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Uploading custom thumbnail: {thumbnail_path}")
    try:
        media = MediaFileUpload(thumbnail_path)
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Thumbnail uploaded successfully.")
        return True
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Failed to upload thumbnail: {e}")
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
            # Treat the parsed time as local time and convert to UTC for the YouTube API
            schedule_iso = schedule_datetime.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Invalid date/time format. Use 'YYYY MM DD' and 'HH:MM'. Error: {e}")
            sys.exit(1)

        # Ensure schedule time is in the future
        current_time = datetime.now()
        if schedule_datetime <= current_time:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Schedule date and time must be in the future.")
            sys.exit(1)

        # Initialize YouTube API client and keep credentials for partner API calls
        youtube, credentials = get_authenticated_service()
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Authentication successful.")

        # Generate a short unique AI-assisted title and store it in used-title history.
        video_title = choose_unique_video_title(video_path)

        # Get video description
        video_description = get_video_description()

        # Prepare video metadata
        request_body = {
            'snippet': {
                'title': video_title,
                'description': video_description,
                'tags': ['historical photos', 'rare history', 'amazing historical photos',
                         'vintage pictures', 'pictures of the past', 'rare historical photos',
                         'historical pictures', 'rare photos', 'historic', 'interesting fact',
                         'old pictures', 'black and white photography', 'photography',
                         '1970s', 'sealed in time', 'old photos', '1950s', 'nostalgia',
                         '1960s', '1900s', '19th century', 'black and white', 'women',
                         'educational', 'history channel', 'history', 'historical',
                         'education', 'documentary', 'vintage', 'hollywood', 'actress',
                         'pinup', 'then and now', 'iconic', 'back then'],
                'categoryId': '22',  # People & Blogs
                'defaultLanguage': 'en',
                'defaultAudioLanguage': 'en'
            },
            'status': {
                'privacyStatus': 'private',
                'publishAt': schedule_iso,
                'selfDeclaredMadeForKids': False,
                'license': 'youtube',
                'containsSyntheticMedia': False
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
        # Upload the custom thumbnail if it exists in the same folder.
        folder_path = os.path.dirname(video_path)
        thumbnail_path = os.path.join(folder_path, 'thumbnail.jpg')
        if not os.path.exists(thumbnail_path):
            for ext in ['.png', '.jpeg', '.webp', '.bmp', '.tiff']:
                candidate = os.path.join(folder_path, f'thumbnail{ext}')
                if os.path.exists(candidate):
                    thumbnail_path = candidate
                    break

        if os.path.exists(thumbnail_path):
            upload_video_thumbnail(youtube, video_id, thumbnail_path)
        else:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No thumbnail file found to upload in {folder_path}.")
        # Add video to configured historical playlist.
        add_video_to_playlist(youtube, video_id)
        # Match past videos by importing the latest video's end-screen setup by default.
        end_screen_added = add_end_screen_from_latest(video_id)
        if not end_screen_added:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: End screen template was not applied automatically.")

        # Note: Monetization is applied automatically via YouTube Studio defaults.
        # No API call needed - the channel will use whatever monetization tier is configured.

    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Fatal error during upload: {e}")
        sys.exit(1)

def resolve_folder_upload(folder_path):
    """
    Given a folder like D:\\Youtube\\TTT\\2026\\03\\20260330-23h, return
    (video_path, schedule_date, schedule_time) where schedule_date is
    'YYYY MM DD' and schedule_time is 'HH:MM'.
    """
    import re
    folder_name = os.path.basename(os.path.normpath(folder_path))
    match = re.fullmatch(r'(\d{4})(\d{2})(\d{2})-(\d{1,2})h', folder_name)
    if not match:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Folder name '{folder_name}' does not match expected format YYYYMMdd-HHh (e.g. 20260330-23h).")
        sys.exit(1)

    year, month, day, hour = match.groups()
    schedule_date = f"{year} {month} {day}"
    schedule_time = f"{int(hour):02d}:00"

    video_extensions = ('.mp4', '.mkv', '.mov', '.avi', '.webm')
    video_path = None
    for fname in os.listdir(folder_path):
        if fname.lower().startswith('combined_slideshow') and fname.lower().endswith(video_extensions):
            video_path = os.path.join(folder_path, fname)
            break

    if video_path is None:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: No 'combined_slideshow' video file found in '{folder_path}'.")
        sys.exit(1)

    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Resolved → video: {video_path}, date: {schedule_date}, time: {schedule_time}")
    return video_path, schedule_date, schedule_time


if __name__ == '__main__':
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Script started with arguments: {sys.argv}")
    if len(sys.argv) != 2:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Usage: python upload_youtube_video.py <folder_path>")
        print(f"Example: python upload_youtube_video.py 'D:\\Youtube\\TTT\\2026\\03\\20260330-23h'")
        sys.exit(1)

    folder_path = sys.argv[1]
    video_path, schedule_date, schedule_time = resolve_folder_upload(folder_path)
    upload_video(video_path, schedule_date, schedule_time)