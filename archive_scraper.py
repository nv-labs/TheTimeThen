import requests
import json
import subprocess
import time
from urllib.parse import quote

def search_collection_items(collection_name, rows=10, year_filter=None):
    """Searches for items in a collection using the Internet Archive Advanced Search API."""
    base_url = "https://archive.org/advancedsearch.php"
    
    q = f"collection:{collection_name}"
    if year_filter:
        q += f" AND date:{year_filter}"
    
    params = {
        'q': q,
        'fl': 'identifier,title,subject,date',
        'rows': rows,
        'output': 'json'
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        items = data.get('response', {}).get('docs', [])
        print(f"Found {len(items)} items in collection '{collection_name}' {'(filtered by year ' + year_filter + ')' if year_filter else ''}")
        return items
    except Exception as e:
        print(f"Error searching collection: {e}")
        return []

def get_image_url(identifier):
    """Fetches metadata for an item and extracts the original (non-thumbnail) JPG/PNG image URL."""
    metadata_url = f"https://archive.org/metadata/{identifier}"
    try:
        response = requests.get(metadata_url)
        response.raise_for_status()
        meta_data = response.json()
        files = meta_data.get('files', [])
        
        # Get the server from metadata, default to 'archive.org' if not available
        server = meta_data.get('server', 'archive.org')
        base_path = f"https://{server}/0/items/" if server != 'archive.org' else "https://archive.org/download/"
        
        # Filter for image files, exclude thumbnails
        image_files = [
            f for f in files
            if f.get('name', '').lower().endswith(('.jpg', '.jpeg', '.png'))
            and not any(term in f.get('name', '').lower() for term in ['thumb', 'thumbnail', 'preview'])
        ]
        
        # Sort by file size (largest first) to prioritize original images
        image_files.sort(key=lambda x: int(x.get('size', 0)), reverse=True)
        
        if image_files:
            selected_file = image_files[0]
            image_url = f"{base_path}{identifier}/{selected_file['name']}"
            print(f"Selected original image: {image_url} (Size: {selected_file.get('size', 'unknown')} bytes)")
            return image_url
        
        # Fallback to constructed original image URL
        fallback_url = f"{base_path}{identifier}/{identifier}_orig.jpg"
        print(f"No suitable image found, using fallback: {fallback_url}")
        return fallback_url
    except Exception as e:
        print(f"Error getting image for {identifier}: {e}")
        return f"https://archive.org/download/{identifier}/{identifier}_orig.jpg"

def process_item_with_sqliterun(identifier, encoded_xml_url, encoded_image_url):
    """Calls sqliterun.py to download and store the item."""
    try:
        result = subprocess.run(
            ['python', 'sqliterun.py', encoded_image_url, encoded_xml_url],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print(f"✅ Successfully processed {identifier}")
            print(result.stdout)
        else:
            print(f"❌ Failed to process {identifier}: {result.stderr}")
    except Exception as e:
        print(f"❌ Error processing {identifier}: {e}")

def main():
    collection_name = 'digitaltransportation_postcards'
    year_filter = '1985'
    max_items = 10
    
    print(f"Searching collection: {collection_name}")
    if year_filter:
        print(f"Filtering by year: {year_filter}")
    
    items = search_collection_items(collection_name, rows=max_items, year_filter=year_filter)
    
    if not items:
        print("No items found. Trying without year filter...")
        items = search_collection_items(collection_name, rows=max_items, year_filter=None)
    
    if not items:
        print("No items found in the collection. Check if the collection exists.")
        return
    
    processed = 0
    for i, item in enumerate(items, 1):
        identifier = item['identifier']
        title = item.get('title', 'Unknown')
        date = item.get('date', 'Unknown')
        
        print(f"\n{'='*60}")
        print(f"Processing item {i}/{len(items)}: {title} (Date: {date})")
        print(f"Identifier: {identifier}")
        print(f"{'='*60}")
        
        xml_url = f"https://archive.org/download/{identifier}/{identifier}_meta.xml"
        image_url = get_image_url(identifier)
        
        # URL-encode the image and XML URLs to handle spaces and special characters
        encoded_image_url = quote(image_url, safe='/:')
        encoded_xml_url = quote(xml_url, safe='/:')
        
        print(f"Image URL: {encoded_image_url}")
        print(f"XML URL: {encoded_xml_url}")
        
        process_item_with_sqliterun(identifier, encoded_xml_url, encoded_image_url)
        processed += 1
        
        if i < len(items):
            time.sleep(2)
    
    print(f"\n✅ Processing complete! Processed {processed} items.")

if __name__ == "__main__":
    main()