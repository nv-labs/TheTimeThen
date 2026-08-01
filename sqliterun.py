import sqlite3
import requests
import os
from PIL import Image
import io
import xml.etree.ElementTree as ET
import sys

def create_image_db(db_name='universal_image_archive.db'):
    """Creates or updates a database for storing files and metadata."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS archived_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            file_size INTEGER,
            file_data BLOB NOT NULL,
            source_url TEXT NOT NULL UNIQUE,
            file_type TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("PRAGMA table_info(archived_files)")
    columns = [info[1] for info in cursor.fetchall()]
    
    new_columns = [
        ('xml_collection', 'TEXT'),
        ('xml_date', 'TEXT'),
        ('xml_subject', 'TEXT'),
        ('xml_language', 'TEXT'),
        ('xml_title', 'TEXT')
    ]
    
    for column_name, column_type in new_columns:
        if column_name not in columns:
            cursor.execute(f'ALTER TABLE archived_files ADD COLUMN {column_name} {column_type}')
    
    conn.commit()
    return conn

def download_and_store_file(conn, image_url, xml_url):
    """Downloads an image and its associated XML metadata, storing them in the database if not a duplicate."""
    image_filename = os.path.basename(image_url)
    
    # Check for duplicate based on source_url
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM archived_files WHERE source_url = ?', (image_url,))
    if cursor.fetchone():
        print(f"Skipping duplicate image: {image_url}")
        return None, None
    
    try:
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        image_blob_data = image_response.content
        actual_size = len(image_blob_data)
        
        xml_response = requests.get(xml_url)
        xml_response.raise_for_status()
        xml_content = xml_response.text
        
        xml_root = ET.fromstring(xml_content)
        metadata = {
            'collection': xml_root.find('collection').text if xml_root.find('collection') is not None else '',
            'date': xml_root.find('date').text if xml_root.find('date') is not None else '',
            'subject': xml_root.find('subject').text if xml_root.find('subject') is not None else '',
            'language': xml_root.find('language').text if xml_root.find('language') is not None else '',
            'title': xml_root.find('title').text if xml_root.find('title') is not None else ''
        }
        
        file_ext = image_filename.split('.')[-1].lower() if '.' in image_filename else 'unknown'
        
        try:
            image = Image.open(io.BytesIO(image_blob_data))
        except:
            raise Exception("Downloaded file is not a valid image")
        
        cursor.execute('''
            INSERT INTO archived_files 
            (filename, file_size, file_data, source_url, file_type, 
             xml_collection, xml_date, xml_subject, xml_language, xml_title) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (image_filename, actual_size, image_blob_data, image_url, file_ext,
              metadata['collection'], metadata['date'], metadata['subject'], 
              metadata['language'], metadata['title']))
        
        file_id = cursor.lastrowid
        conn.commit()
        return file_id, image_filename
        
    except Exception as e:
        raise

def main():
    DATABASE_NAME = 'universal_image_archive.db'
    
    # Check for command-line arguments
    if len(sys.argv) != 3:
        print("Usage: python sqliterun.py <image_url> <xml_url>")
        sys.exit(1)
    
    IMAGE_URL = sys.argv[1]
    XML_URL = sys.argv[2]
    
    conn = None
    success_count = 0
    
    try:
        conn = create_image_db(DATABASE_NAME)
        file_id, filename = download_and_store_file(conn, IMAGE_URL, XML_URL)
        if file_id is not None:  # Only count non-duplicate images
            success_count += 1
    except Exception as e:
        print(f"Operation failed: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()
    
    print(f"Successfully downloaded {success_count} images.")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    main()