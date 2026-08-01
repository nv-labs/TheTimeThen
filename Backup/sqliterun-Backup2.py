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
            source_url TEXT NOT NULL,
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
            print(f"Added column '{column_name}' to archived_files table")
    
    conn.commit()
    print(f"Database '{db_name}' initialized successfully.")
    return conn

def download_and_store_file(conn, image_url, xml_url):
    """Downloads an image and its associated XML metadata, storing them in the database."""
    image_filename = os.path.basename(image_url)
    
    print(f"Downloading image from: {image_url}")
    print(f"Downloading XML from: {xml_url}")
    
    try:
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        image_blob_data = image_response.content
        actual_size = len(image_blob_data)
        print(f"Downloaded image: {actual_size} bytes")
        
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
            print(f"File is a valid {image.format} image: {image.size[0]}x{image.size[1]} pixels")
        except:
            print(f"File is not a recognizable image format")
            raise Exception("Downloaded file is not a valid image")
        
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO archived_files 
            (filename, file_size, file_data, source_url, file_type, 
             xml_collection, xml_date, xml_subject, xml_language, xml_title) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (image_filename, actual_size, image_blob_data, image_url, file_ext,
              metadata['collection'], metadata['date'], metadata['subject'], 
              metadata['language'], metadata['title']))
        
        file_id = cursor.lastrowid
        conn.commit()
        print(f"Stored '{image_filename}' with XML metadata in database with ID {file_id}")
        return file_id, image_filename
        
    except Exception as e:
        print(f"Error: {e}")
        raise

def display_image_if_available(conn, file_id):
    """Displays the image and its metadata."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT filename, file_data, file_type, xml_collection, xml_date, 
               xml_subject, xml_language, xml_title 
        FROM archived_files WHERE id = ?
    ''', (file_id,))
    result = cursor.fetchone()
    
    if not result:
        print(f"No file found with ID {file_id}")
        return
    
    filename, blob_data, file_type, xml_collection, xml_date, xml_subject, xml_language, xml_title = result
    
    print(f"\n{'='*50}")
    print(f"File: {filename}")
    print(f"Metadata:")
    print(f"   Collection: {xml_collection or 'N/A'}")
    print(f"   Date: {xml_date or 'N/A'}")
    print(f"   Subject: {xml_subject or 'N/A'}")
    print(f"   Language: {xml_language or 'N/A'}")
    print(f"   Title: {xml_title or 'N/A'}")
    print(f"{'='*50}")
    
    try:
        image = Image.open(io.BytesIO(blob_data))
        
        print(f"Image format: {image.format}")
        print(f"Dimensions: {image.size[0]} x {image.size[1]} pixels")
        print(f"Color mode: {image.mode}")
        
        print("Opening image in default viewer...")
        image.show()
        
        output_name = f"display_{file_id}.{image.format.lower()}"
        image.save(output_name)
        print(f"Image saved as: {output_name}")
        
    except Exception as e:
        print(f"Error displaying image: {e}")
        print("This file is not a recognizable image format.")
        print("The file might be:")
        print("   - A SQLite database")
        print("   - A text file")
        print("   - A binary file in a non-image format")
        print("   - A corrupted image file")
        
        output_name = f"original_{filename}"
        with open(output_name, 'wb') as f:
            f.write(blob_data)
        print(f"Original file saved as: {output_name} for inspection")

def main():
    DATABASE_NAME = 'universal_image_archive.db'
    
    # Check for command-line arguments
    if len(sys.argv) != 3:
        print("Usage: python sqliterun.py <image_url> <xml_url>")
        sys.exit(1)
    
    IMAGE_URL = sys.argv[1]
    XML_URL = sys.argv[2]
    
    conn = None
    try:
        conn = create_image_db(DATABASE_NAME)
        
        print(f"\n{'='*60}")
        print(f"Processing image and XML")
        print(f"{'='*60}")
        
        file_id, filename = download_and_store_file(conn, IMAGE_URL, XML_URL)
        display_image_if_available(conn, file_id)
        
        print("Image and metadata successfully downloaded and displayed!")
        print("-" * 40)
        
    except Exception as e:
        print(f"Operation failed: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # Ensure UTF-8 encoding for console output
    sys.stdout.reconfigure(encoding='utf-8')
    main()