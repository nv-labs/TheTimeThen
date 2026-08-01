import sqlite3
from datetime import datetime

def update_video_airdate(db_name='universal_image_archive.db'):
    """Update records with no VideoAirDate to the latest VideoAirDate in the database."""
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Get the latest VideoAirDate
        cursor.execute("SELECT MAX(VideoAirDate) FROM archived_files WHERE VideoAirDate IS NOT NULL AND VideoAirDate != ''")
        latest_airdate = cursor.fetchone()[0]

        if not latest_airdate:
            print("No valid VideoAirDate found in the database. No updates performed.")
            return

        # Update records where VideoAirDate is NULL or empty
        cursor.execute("""
            UPDATE archived_files
            SET VideoAirDate = ?
            WHERE VideoAirDate IS NULL OR VideoAirDate = ''
        """, (latest_airdate,))

        # Get the number of affected rows
        updated_count = cursor.rowcount
        conn.commit()

        print(f"Successfully updated {updated_count} records with VideoAirDate '{latest_airdate}'.")

    except Exception as e:
        print(f"Error updating VideoAirDate: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_video_airdate()