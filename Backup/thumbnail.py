import sqlite3
import os
import sys
from datetime import datetime

def download_last_images(output_dir, db_name='universal_image_archive.db', num_images=17):
    """Download the last num_images images with non-empty VideoAirDate to the specified output directory."""
    try:
        # Validate output directory
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        elif not os.path.isdir(output_dir):
            print(f"Error: '{output_dir}' is not a directory.")
            return 0

        # Connect to the database
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Verify the table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='archived_files'")
        if not cursor.fetchone():
            print(f"Error: Table 'archived_files' does not exist in database '{db_name}'.")
            conn.close()
            return 0

        # Fetch the last num_images with non-empty VideoAirDate, ordered by added_date DESC
        cursor.execute('''
            SELECT filename, file_data
            FROM archived_files
            WHERE VideoAirDate IS NOT NULL AND VideoAirDate != ''
            ORDER BY added_date DESC
            LIMIT ?
        ''', (num_images,))

        rows = cursor.fetchall()

        if not rows:
            print("No images with non-empty VideoAirDate found in the database.")
            conn.close()
            return 0

        saved_count = 0
        for filename, file_data in rows:
            output_path = os.path.join(output_dir, filename)
            try:
                # Ensure the output path is unique
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(output_path):
                    output_path = os.path.join(output_dir, f"{base}_{counter}{ext}")
                    counter += 1

                # Save the image
                with open(output_path, 'wb') as f:
                    f.write(file_data)
                print(f"✅ Saved image '{filename}' to '{output_path}'")
                saved_count += 1
            except Exception as e:
                print(f"❌ Error saving image '{filename}': {e}")

        print(f"\nFinished. Successfully saved {saved_count} images to '{output_dir}'.")
        conn.close()
        return saved_count

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 0
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python download_last_images.py <output_directory>")
        print("Example: python download_last_images.py \"D:\\Youtube\\TTT\\20251012B\"")
        sys.exit(1)

    output_dir = sys.argv[1]
    download_last_images(output_dir)