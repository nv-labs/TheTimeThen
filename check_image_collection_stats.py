import sqlite3
import os

DB_DIR = r"D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\databases"
DB_NAME = os.path.join(DB_DIR, "image_collection.db")
TABLE_NAME = "image_comp"

def check_db_stats():
    if not os.path.exists(DB_NAME):
        print(f"❌ Database file '{DB_NAME}' not found.")
        return

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Total number of rows
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        total_rows = cursor.fetchone()[0]

        # Number of rows with VideoAirDate NOT NULL and NOT empty
        cursor.execute(f"""
            SELECT COUNT(*) FROM {TABLE_NAME}
            WHERE VideoAirDate IS NOT NULL AND VideoAirDate != ''
        """)
        with_date = cursor.fetchone()[0]

        # Number of rows with VideoAirDate NULL or empty
        without_date = total_rows - with_date

        # Min and Max VideoAirDate (only if there are any)
        if with_date > 0:
            cursor.execute(f"""
                SELECT MIN(VideoAirDate), MAX(VideoAirDate)
                FROM {TABLE_NAME}
                WHERE VideoAirDate IS NOT NULL AND VideoAirDate != ''
            """)
            min_date, max_date = cursor.fetchone()
        else:
            min_date = max_date = None

        print(f"Database Statistics for '{DB_NAME}' -> table '{TABLE_NAME}':")
        print(f"   Total images:                {total_rows}")
        print(f"   With VideoAirDate set:       {with_date}")
        print(f"   Without VideoAirDate:        {without_date}")

        if with_date > 0:
            print(f"   Earliest VideoAirDate:       {min_date}")
            print(f"   Latest VideoAirDate:         {max_date}")
            print("Some images have already been used in videos.")
        else:
            print("No images have been used in videos yet (all VideoAirDate empty).")

        conn.close()

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    check_db_stats()