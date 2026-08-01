import sqlite3
import shutil
import os
from datetime import datetime

def backup_database(db_name='universal_image_archive.db', backup_dir='backups'):
    """Create a backup of the SQLite database with a timestamped filename."""
    try:
        # Ensure the database file exists
        if not os.path.exists(db_name):
            print(f"Error: Database file '{db_name}' does not exist.")
            return

        # Create backup directory if it doesn't exist
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            print(f"Created backup directory: '{backup_dir}'")

        # Generate timestamp for the backup filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"universal_image_archive_backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Copy the database file to the backup location
        shutil.copy2(db_name, backup_path)
        print(f"Successfully created backup: '{backup_path}'")

    except Exception as e:
        print(f"Error creating backup: {e}")

if __name__ == "__main__":
    backup_database()