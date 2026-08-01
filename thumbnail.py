import sqlite3
import os
import sys
from PIL import Image
import io
from datetime import datetime
from multiprocessing import Pool, cpu_count

def create_indexes(conn):
    """Create indexes on VideoAirDate and added_date to improve query performance."""
    try:
        cursor = conn.cursor()
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_airdate ON archived_files (VideoAirDate)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_added_date ON archived_files (added_date)')
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error creating indexes: {e}")
        return False

def process_thumbnail(args):
    """Process an image to create a thumbnail and save it to the output directory."""
    output_dir, filename, file_data = args
    try:
        img = Image.open(io.BytesIO(file_data)).convert('RGB')
        img.thumbnail((1280, 720), Image.Resampling.LANCZOS)

        base, ext = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"thumb_{filename}")
        counter = 1
        while os.path.exists(output_path):
            output_path = os.path.join(output_dir, f"thumb_{base}_{counter}{ext}")
            counter += 1

        img.save(output_path, quality=85)
        return f"✅ Saved thumbnail '{filename}'", True
    except Exception as e:
        return f"❌ Error processing '{filename}': {e}", False

def create_thumbnails(output_dir, db_name='universal_image_archive.db', max_images=20):
    """Create thumbnails for up to max_images from the most recent VideoAirDate group."""
    conn = None
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        elif not os.path.isdir(output_dir):
            print(f"Error: '{output_dir}' is not a directory.")
            return 0

        conn = sqlite3.connect(db_name)
        create_indexes(conn)
        cursor = conn.cursor()

        # Ensure the table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='archived_files'")
        if not cursor.fetchone():
            print(f"Error: Table 'archived_files' does not exist in '{db_name}'.")
            return 0

        # ✅ Step 1: Get the most recent exact VideoAirDate (with hour/minute precision)
        cursor.execute('''
            SELECT VideoAirDate
            FROM archived_files
            WHERE VideoAirDate IS NOT NULL AND TRIM(VideoAirDate) != ''
            ORDER BY datetime(VideoAirDate) DESC
            LIMIT 1
        ''')
        latest_date_row = cursor.fetchone()

        if not latest_date_row:
            print("No valid VideoAirDate entries found.")
            return 0

        latest_date = latest_date_row[0]
        print(f"📅 Latest VideoAirDate detected: {latest_date}")

        # ✅ Step 2: Fetch up to `max_images` entries that match that exact datetime
        cursor.execute('''
            SELECT filename, file_data
            FROM archived_files
            WHERE TRIM(VideoAirDate) = TRIM(?)
            ORDER BY added_date DESC
            LIMIT ?
        ''', (latest_date, max_images))

        rows = cursor.fetchall()

        if not rows:
            print(f"No images found for VideoAirDate = {latest_date}")
            return 0

        process_args = [(output_dir, filename, file_data) for filename, file_data in rows]

        with Pool(processes=cpu_count()) as pool:
            results = pool.map(process_thumbnail, process_args)

        saved_count = sum(1 for _, success in results if success)
        for message, _ in results:
            print(message)

        print(f"\n✅ Finished: Created {saved_count} thumbnails from VideoAirDate '{latest_date}' in '{output_dir}'.")
        return saved_count

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 0
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python thumbnail_optimized.py <output_directory>")
        print("Example: python thumbnail_optimized.py \"D:\\Youtube\\TTT\\20251013B\"")
        sys.exit(1)

    output_dir = sys.argv[1]
    create_thumbnails(output_dir)
