import requests
from bs4 import BeautifulSoup
import os
import shutil
import urllib.parse
import time

# Folder to save images
SAVE_FOLDER = "copyright_free_images"

# Create folder if it doesn't exist
if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)

def get_full_image_url(image_page_url, headers):
    """Fetch the full-resolution image URL from the image's Wikimedia page."""
    try:
        response = requests.get(image_page_url, headers=headers, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        # Find the full-resolution image link
        full_image_div = soup.find("div", class_="fullImageLink")
        if full_image_div:
            img_tag = full_image_div.find("a")
            if img_tag and img_tag.get("href"):
                return img_tag["href"]
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching image page {image_page_url}: {e}")
        return None

def search_and_download_images(query="landscape", num_images=10):
    # Wikimedia Commons search URL
    search_query = urllib.parse.quote(query)
    url = f"https://commons.wikimedia.org/w/index.php?search={search_query}&title=Special:MediaSearch&type=image"

    # Headers to mimic a browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        # Make request to Wikimedia Commons
        print(f"Searching for images with query: {query}")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Find image result links (links to image pages)
        image_links = soup.find_all("a", class_="sdms-image-result")
        image_urls = []
        for link in image_links:
            href = link.get("href")
            if href and href.startswith("/wiki/File:"):
                full_image_page_url = f"https://commons.wikimedia.org{href}"
                full_image_url = get_full_image_url(full_image_page_url, headers)
                if full_image_url and full_image_url.endswith((".jpg", ".jpeg", ".png")):
                    image_urls.append(full_image_url)
                    if len(image_urls) >= num_images:
                        break

        if not image_urls:
            print(f"No suitable images found for query '{query}' on Wikimedia Commons.")
            print("Try a different query (e.g., 'wildlife', 'art', 'nature') or check https://commons.wikimedia.org/ manually.")
            return

        print(f"Found {len(image_urls)} image URLs: {image_urls}")

        # Download images
        downloaded = 0
        for i, img_url in enumerate(image_urls[:num_images]):
            try:
                img_response = requests.get(img_url, stream=True, headers=headers, timeout=5)
                img_response.raise_for_status()

                # Determine file extension
                ext = ".jpg" if img_url.endswith((".jpg", ".jpeg")) else ".png"
                image_name = f"image_{i+1}{ext}"
                image_path = os.path.join(SAVE_FOLDER, image_name)

                # Save image
                with open(image_path, "wb") as f:
                    shutil.copyfileobj(img_response.raw, f)
                print(f"Downloaded {image_name}")
                downloaded += 1
                time.sleep(1)  # Delay to avoid rate limiting
            except requests.exceptions.RequestException as e:
                print(f"Failed to download {img_url}: {e}")
                continue

        print(f"Successfully downloaded {downloaded} images to {SAVE_FOLDER}")

    except requests.exceptions.RequestException as e:
        print(f"Error searching for images: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Download 10 copyright-free images
    search_and_download_images(query="landscape", num_images=10)