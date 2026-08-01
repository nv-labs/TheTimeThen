import sqlite3
import os
import sys

def check_empty_video_air_date(db_name='D:\\Dev\\TheTimeThen\\universal_image_archive.db'):
    """Check the count of records in archived_files where VideoAirDate is empty or NULL."""
    try:
        # Verify database file exists and is readable
        if not os.path.exists(db_name):
            print(f"Error: Database file {db_name} does not exist.")
            sys.exit(1)
        if not os.access(db_name, os.R_OK):
            print(f"Error: Database file {db_name} is not readable. Check permissions.")
            sys.exit(1)

        # Connect to the database
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Query to count records with empty or NULL VideoAirDate
        cursor.execute('''
            SELECT COUNT(*) 
            FROM archived_files 
            WHERE VideoAirDate = '' OR VideoAirDate IS NULL
        ''')
        count = cursor.fetchone()[0]

        print(f"Number of records with empty or NULL VideoAirDate: {count}")

        # Optional: List some sample records for verification
        cursor.execute('''
            SELECT id, xml_title 
            FROM archived_files 
            WHERE VideoAirDate = '' OR VideoAirDate IS NULL 
            LIMIT 5
        ''')
        samples = cursor.fetchall()
        if samples:
            print("\nSample records with empty or NULL VideoAirDate:")
            for row in samples:
                print(f"ID {row[0]}: {row[1]}")
        else:
            print("\nNo sample records to display.")

    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    # Default database path; can be overridden via command-line argument
    db_path = 'D:\\Dev\\TheTimeThen\\universal_image_archive.db'
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    check_empty_video_air_date(db_path)
