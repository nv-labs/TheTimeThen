import sqlite3
import sys

def reset_video_air_date(video_air_date, db_name='universal_image_archive.db'):
    """Reset VideoAirDate to NULL for records matching the input VideoAirDate."""
    try:
        # Connect to the database
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Verify the table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='archived_files'")
        if not cursor.fetchone():
            print(f"Error: Table 'archived_files' does not exist in database '{db_name}'.")
            return 0

        # Update VideoAirDate to NULL for matching records
        cursor.execute('''
            UPDATE archived_files
            SET VideoAirDate = NULL
            WHERE VideoAirDate = ?
        ''', (video_air_date,))

        # Get the number of affected rows
        affected_rows = cursor.rowcount
        conn.commit()

        if affected_rows > 0:
            print(f"Successfully reset VideoAirDate for {affected_rows} records with VideoAirDate '{video_air_date}'.")
        else:
            print(f"No records found with VideoAirDate '{video_air_date}'.")

        return affected_rows

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
        print("Usage: python reset_video_air_date.py <video_air_date>")
        print("Example: python reset_video_air_date.py '2025-10-11 17'")
        sys.exit(1)

    video_air_date = sys.argv[1]
    reset_video_air_date(video_air_date)