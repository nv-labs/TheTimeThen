import sqlite3
import os
import json
import glob
from PIL import Image
import io
from datetime import datetime
import re
from tqdm import tqdm

def create_photos_db(db_name='universal_image_archive.db', schema_name='photos_2023'):
    """Creates or connects to the photos table with a schema-like prefix in SQLite."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Optimize SQLite performance
    cursor.execute("PRAGMA cache_size = -20000")  # 20MB cache
    cursor.execute("PRAGMA journal_mode = WAL")  # Use Write-Ahead Logging

    # Use schema_name as a prefix for the table name
    table_name = f"{schema_name}_photos"

    # Check if the table exists
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if not cursor.fetchone():
        cursor.execute(f"""
            CREATE TABLE {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_size INTEGER,
                file_data BLOB NOT NULL,
                source_url TEXT NOT NULL,
                file_type TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                xml_collection TEXT,
                xml_date TEXT,
                xml_subject TEXT,
                xml_language TEXT,
                xml_title TEXT UNIQUE,
                description TEXT,
                photo_taken_time TEXT
            )
        """)
        conn.commit()
        print(f"Created {table_name} table")

    return conn

def get_metadata_file(image_path):
    """Find the corresponding metadata file for an image."""
    filename = os.path.basename(image_path)
    folder_path = os.path.dirname(image_path)
    base_name = os.path.splitext(filename)[0]

    # Extract the number(s) from the filename
    number_match = re.match(r'image\((\d+)\)(?:\((\d+)\))?\.png$', filename)
    if not number_match:
        print(f"⚠️ Filename '{filename}' does not match expected pattern. Trying fallback.")
        # Fallback: check for standard metadata file (e.g., image(X).png.supplemental-metadata)
        metadata_path = os.path.join(folder_path, f"{base_name}.supplemental-metadata")
        if os.path.exists(metadata_path):
            return metadata_path
        return None

    main_number = number_match.group(1)  # e.g., '8796' in image(8796).png
    sub_number = number_match.group(2)  # e.g., 'Y' in image(X)(Y).png, or None

    if sub_number:
        # For image(X)(Y).png, look for image(X).png.supplemental-metadata(Y).json
        metadata_path = os.path.join(folder_path, f"image({main_number}).png.supplemental-metadata({sub_number}).json")
        if os.path.exists(metadata_path):
            return metadata_path
    else:
        # For image(X).png, look for image.png.supplemental-metadata(X).json first
        metadata_path = os.path.join(folder_path, f"image.png.supplemental-metadata({main_number}).json")
        if os.path.exists(metadata_path):
            return metadata_path
        # Fallback to image(X).png.supplemental-metadata
        metadata_path = os.path.join(folder_path, f"image({main_number}).png.supplemental-metadata")
        if os.path.exists(metadata_path):
            return metadata_path
        # Check for image(X).png.supplemental-metadata(<number>).json
        for i in range(1, 10000):
            numbered_metadata = os.path.join(folder_path, f"image({main_number}).png.supplemental-metadata({i}).json")
            if os.path.exists(numbered_metadata):
                return numbered_metadata

    return None

def insert_photos_with_metadata(folder_path, db_name='universal_image_archive.db', schema_name='photos_2023'):
    """Insert photos with metadata into the photos table with a schema-like prefix, with a progress bar."""
    if not os.path.isdir(folder_path):
        print(f"Error: '{folder_path}' is not a valid directory.")
        return 0

    conn = create_photos_db(db_name, schema_name)
    cursor = conn.cursor()
    success_count = 0

    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp', '*.tiff']
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(folder_path, ext)))
    image_files = sorted(list(set(image_files)))

    if not image_files:
        print("No images found in the specified folder.")
        conn.close()
        return 0

    print(f"Found {len(image_files)} image files in '{folder_path}'.")

    table_name = f"{schema_name}_photos"

    with tqdm(total=len(image_files), desc="Processing images", unit="image") as pbar:
        for image_path in image_files:
            filename = os.path.basename(image_path)
            metadata_path = get_metadata_file(image_path)

            if not metadata_path:
                print(f"⚠️ No metadata file found for '{filename}'. Skipping.")
                pbar.update(1)
                continue

            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                description = metadata.get('description', '').strip()
                photo_taken_time = metadata.get('photoTakenTime', {}).get('formatted', '')
            except Exception as e:
                print(f"❌ Error reading metadata for '{filename}': {e}. Skipping.")
                pbar.update(1)
                continue

            if not description:
                print(f"⚠️ Empty description in metadata for '{filename}'. Skipping.")
                pbar.update(1)
                continue

            cursor.execute(f"SELECT id FROM {table_name} WHERE xml_title = ?", (description,))
            if cursor.fetchone():
                print(f"⚠️ Description '{description}' already exists in {table_name} for '{filename}'. Skipping.")
                pbar.update(1)
                continue

            try:
                with open(image_path, 'rb') as f:
                    file_data = f.read()
                Image.open(io.BytesIO(file_data))  # Verify image validity
            except Exception as e:
                print(f"❌ Invalid image '{filename}': {e}. Skipping.")
                pbar.update(1)
                continue

            file_size = len(file_data)
            file_ext = os.path.splitext(filename)[1][1:].lower() if '.' in filename else 'unknown'
            source_url = metadata.get('url', image_path)

            try:
                cursor.execute(f"""
                    INSERT INTO {table_name} (
                        filename, file_size, file_data, source_url, file_type, added_date,
                        xml_collection, xml_date, xml_subject, xml_language, xml_title,
                        description, photo_taken_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    filename, file_size, file_data, source_url, file_ext, datetime.now(),
                    '', photo_taken_time, '', '', description, description, photo_taken_time
                ))
                conn.commit()
                success_count += 1
                print(f"✅ Inserted '{filename}' with xml_title '{description}' into {table_name}")
            except sqlite3.IntegrityError as e:
                print(f"⚠️ Failed to insert '{filename}': {e}. Likely duplicate xml_title.")
            except Exception as e:
                print(f"❌ Error inserting '{filename}': {e}. Skipping.")
            
            pbar.update(1)

    conn.close()
    print(f"\nFinished. Successfully added {success_count} photos to {table_name} table.")
    return success_count

if __name__ == "__main__":
    folder_path = r"D:\Pictures\2023\Takeout\Google Foto_s\Foto_s van 2023"
    insert_photos_with_metadata(folder_path)