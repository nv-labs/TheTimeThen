import sqlite3
from datetime import datetime

def reset_video_air_date(db_name='universal_image_archive.db', reset_date='2025-11-03'):
    """
    Resets VideoAirDate to an empty string ('') for records with VideoAirDate on or after the specified date.
    Returns the number of affected rows.
    """
    try:
        # Connect to the database
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Query to count rows to be updated
        cursor.execute('''
            SELECT COUNT(*) 
            FROM archived_files 
            WHERE VideoAirDate IS NOT NULL 
            AND VideoAirDate >= ?
        ''', (reset_date,))

        count = cursor.fetchone()[0]

        # Update VideoAirDate to empty string ('') for records on or after reset_date
        cursor.execute('''
            UPDATE archived_files 
            SET VideoAirDate = '' 
            WHERE VideoAirDate IS NOT NULL 
            AND VideoAirDate >= ?
        ''', (reset_date,))

        # Commit the changes
        conn.commit()

        # Verify the number of rows affected
        print(f"Updated {count} records by setting VideoAirDate to '' for dates on or after {reset_date}.")

        return count

    except Exception as e:
        print(f"Error during database operation: {e}")
        return 0

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # Run the reset operation
    affected_rows = reset_video_air_date()
    print(f"Total records changed: {affected_rows}")