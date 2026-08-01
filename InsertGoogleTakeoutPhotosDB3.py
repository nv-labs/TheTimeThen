import os
import sqlite3
import json
import hashlib
import re
from datetime import datetime
import random
import argparse
import sys

def create_database(db_path):
    """Create a new SQLite database with the required schema."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create the photos table with additional categories
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            file_size INTEGER,
            file_data BLOB,
            source_path TEXT,
            file_type TEXT,
            added_date TEXT,
            taken_date TEXT,
            category TEXT,
            xml_title TEXT,
            description TEXT,
            json_metadata TEXT,
            VideoAirDate TEXT
        )
    ''')

    # Create the categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT UNIQUE
        )
    ''')

    conn.commit()
    conn.close()

def insert_categories(conn, categories):
    """Insert categories into the categories table."""
    cursor = conn.cursor()
    for category in categories:
        try:
            cursor.execute("INSERT OR IGNORE INTO categories (category_name) VALUES (?)", (category,))
        except sqlite3.IntegrityError:
            pass
    conn.commit()

def insert_photo(conn, photo_data):
    """Insert a photo and its metadata into the photos table."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO photos (
            filename, file_size, file_data, source_path, file_type, added_date, 
            taken_date, category, xml_title, description, json_metadata, VideoAirDate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        photo_data['filename'],
        photo_data['file_size'],
        photo_data['file_data'],
        photo_data['source_path'],
        photo_data['file_type'],
        photo_data['added_date'],
        photo_data['taken_date'],
        photo_data['category'],
        photo_data['xml_title'],
        photo_data['description'],
        json.dumps(photo_data['json_metadata']),
        photo_data['VideoAirDate']
    ))
    conn.commit()

def resolve_image_file(metadata_file, metadata_title):
    """Resolve the real image/video file path for a Google Takeout metadata file."""
    directory = os.path.dirname(metadata_file)
    metadata_name = os.path.basename(metadata_file)

    match = re.match(r"^(?P<title>.+?)\.supplemental-metadata(?:\((?P<idx>\d+)\))?\.json$", metadata_name)
    if not match:
        return None

    title = metadata_title or match.group("title")
    idx = match.group("idx")
    stem, ext = os.path.splitext(title)

    candidates = []
    if idx:
        candidates.append(os.path.join(directory, f"{stem}({idx}){ext}"))
    candidates.append(os.path.join(directory, title))
    candidates.append(os.path.join(directory, match.group("title")))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return None


def process_metadata_file(metadata_file):
    """Process a .supplemental-metadata.json file and return photo data."""
    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    image_file = resolve_image_file(metadata_file, metadata.get('title'))

    if not image_file:
        print(f"Warning: Could not resolve image filename for metadata: {metadata_file}")
        return None

    # Check if the image file exists
    if not os.path.exists(image_file):
        print(f"Warning: Image file not found for metadata: {metadata_file}")
        return None

    # Read the image file as binary data
    with open(image_file, 'rb') as img_f:
        file_data = img_f.read()

    description = metadata.get('description', '')
    title = metadata['title']
    
    photo_data = {
        'filename': title,
        'file_size': os.path.getsize(image_file),
        'file_data': file_data,  # Store binary data
        'source_path': image_file,  # Use local file path
        'file_type': title.split('.')[-1],
        'added_date': datetime.now().isoformat(),
        'taken_date': metadata['photoTakenTime']['formatted'],
        'category': 'Uncategorized',  # Default category
        'xml_title': description if description else title,  # Use description or filename
        'description': description,
        'json_metadata': metadata,
        'VideoAirDate': None  # Placeholder for video air date
    }

    return photo_data

def process_images(input_folder, db_path, categories, limit=None):
    """Process images and their metadata from the input folder."""
    conn = sqlite3.connect(db_path)

    # Insert categories into the database
    insert_categories(conn, categories)

    processed_count = 0
    skipped_count = 0
    metadata_total = sum(
        1
        for root, _, files in os.walk(input_folder)
        for file in files
        if file.endswith('.json') and 'supplemental-metadata' in file
    )

    for root, _, files in os.walk(input_folder):
        for file in files:
            if file.endswith('.json') and 'supplemental-metadata' in file:
                metadata_file = os.path.join(root, file)

                # Process metadata file and get photo data
                photo_data = process_metadata_file(metadata_file)

                # Skip if photo_data is None (e.g., image file not found)
                if photo_data is None:
                    skipped_count += 1
                    print(f"Skipping: {metadata_file}")
                    continue

                # Assign a random category
                photo_data['category'] = random.choice(categories)

                # Insert photo data into the database
                insert_photo(conn, photo_data)

                processed_count += 1
                print(f"Processed {processed_count}/{metadata_total} metadata files (skipped: {skipped_count})", end="\r")
                sys.stdout.flush()

                if limit and processed_count >= abs(limit):
                    print(f"Processed {processed_count} images (limit reached).")
                    conn.close()
                    return

    print(f"Finished processing {processed_count} images. Skipped {skipped_count} metadata files.")
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process Google Takeout photos and metadata.")
    parser.add_argument("--input_folder", type=str, default="D:\\Pictures\\2023\\Takeout\\Google Foto_s", help="Path to the input folder containing Google Takeout photos.")
    parser.add_argument("--db_path", type=str, default="d:/Dev/TheTimeThen/google_takeout_photos_2023.db", help="Path to the SQLite database.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of images to process. Use negative value to process the first N images.")

    args = parser.parse_args()

    categories = [f"Category {i}" for i in range(1, 251)]  # Generate 250 categories

    create_database(args.db_path)
    process_images(args.input_folder, args.db_path, categories, args.limit)