import os
import pickle
from datetime import datetime
import requests
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import AuthorizedSession
import io

# --- Configuration ---
# Scopes required for Google Photos API
SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']
# The base URL for the Photos Library API
PHOTOS_BASE_URL = 'https://photoslibrary.googleapis.com/v1'

# --- Authentication Function ---

def authenticate_google_photos():
    """
    Authenticates the user and returns the Google Credentials object.
    It handles token refreshing and local storage in 'token.pickle'.
    """
    creds = None
    # Load credentials if they exist
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If creds are invalid, refresh them or start the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing existing token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}. Will attempt full re-auth.")
                creds = None
        
        if not creds:
            print("Starting new OAuth flow...")
            try:
                # Flow handles the browser login process
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            except FileNotFoundError:
                print("Error: credentials.json not found in the script directory.")
                raise
            except Exception as e:
                print(f"Error during OAuth flow: {e}")
                raise
        
        # Save credentials for next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
            
    return creds

# --- Download Function ---

def download_images(session, max_results=10, cutoff_date_str='2024-08-19'):
    """
    Searches for and downloads images created on or before the cutoff date 
    using the authenticated HTTP session.
    """
    
    # Convert the string date to datetime object to extract parts
    date_parts = datetime.strptime(cutoff_date_str, '%Y-%m-%d')
    
    # --- CORRECTED DATE FILTER STRUCTURE ---
    # The API requires ranges to be provided under a 'ranges' key in a list.
    date_filter = {
        'dateFilter': {
            'ranges': [
                {
                    'startDate': {
                        'year': 1970, # Earliest year possible
                        'month': 1,
                        'day': 1
                    },
                    'endDate': {
                        'day': date_parts.day,
                        'month': date_parts.month,
                        'year': date_parts.year
                    }
                }
            ]
        }
    }
    # ---------------------------------------

    # Build the final search body
    search_body = {
        'filters': {
            'mediaTypeFilter': {
                'mediaTypes': ['PHOTO']
            },
            **date_filter # Merge the correctly structured date filter
        },
        'pageSize': max_results,
    }
    
    # Send the search request using the AuthorizedSession
    print(f"Searching for up to {max_results} images before or on {cutoff_date_str}...")
    try:
        response = session.post(
            f'{PHOTOS_BASE_URL}/mediaItems:search', 
            json=search_body
        )
        response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx or 5xx)
        results = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error during mediaItems search: {e}")
        # Print the API error response if available for better debugging
        try:
            print(f"API Error Details: {response.json()}")
        except Exception:
            pass
        return

    items = results.get('mediaItems', [])
    print(f'Found {len(items)} images matching the criteria.')
    
    # Create downloads folder
    os.makedirs('downloads', exist_ok=True)
    
    downloaded = 0
    for item in items:
        if downloaded >= max_results:
            break
            
        filename = item['filename']
        # Append '=d' to baseUrl to get the original/download quality URL
        download_url = item['baseUrl'] + '=d'
        
        # Download the image using a standard requests.get()
        print(f'Attempting to download: {filename}')
        try:
            # Use requests.get(stream=True) for efficient downloading
            image_response = requests.get(download_url, stream=True)
            image_response.raise_for_status() 
            
            filepath = os.path.join('downloads', filename)
            with open(filepath, 'wb') as f:
                for chunk in image_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            downloaded += 1
            print(f'Successfully downloaded {filename}')
            
        except requests.exceptions.RequestException as e:
            print(f"Error downloading {filename}: {e}")
        
    print(f'\n--- Download complete: {downloaded} images saved to ./downloads/ ---')

# --- Main Execution ---

if __name__ == '__main__':
    try:
        # 1. Authenticate and get credentials
        creds = authenticate_google_photos()
        
        # 2. Create an AuthorizedSession using the credentials
        authed_session = AuthorizedSession(creds)
        
        # 3. Execute the download logic
        download_images(authed_session)
        
    except Exception as e:
        print(f"\nFATAL ERROR: The script could not complete due to: {e}")