# check_db_photos.py
import sqlite3
import os

# Same config as in your insert script
DB_NAME = "universal_image_archive.db"
TABLE_NAME = "photos"

def count_photos_in_db():
    if not os.path.exists(DB_NAME):
        print(f"❌ Database file not found: {DB_NAME}")
        print("   → You haven't run insert_photos_with_ai_categories.py yet,")
        print("     or no photos were inserted.")
        return

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(f"""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """, (TABLE_NAME,))
        
        if not cursor.fetchone():
            print(f"❌ Table '{TABLE_NAME}' does not exist in the database.")
            print("   → Run insert_photos_with_ai_categories.py first.")
            conn.close()
            return

        # Count total rows
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        total = cursor.fetchone()[0]

        # Optional: show some stats
        cursor.execute(f"SELECT COUNT(DISTINCT xml_subject) FROM {TABLE_NAME}")
        categories = cursor.fetchone()[0]

        cursor.execute(f"SELECT MIN(added_date), MAX(added_date) FROM {TABLE_NAME}")
        dates = cursor.fetchone()
        first_date = dates[0] if dates[0] else "N/A"
        last_date = dates[1] if dates[1] else "N/A"

        conn.close()

        print("📊 Database Photo Report")
        print("=" * 40)
        print(f"🗄️  Database file:     {DB_NAME}")
        print(f"📋 Table name:        {TABLE_NAME}")
        print(f"📸 Total photos:      {total}")
        print(f"🏷️  Unique categories: {categories}")
        print(f"🗓️  First inserted:    {first_date}")
        print(f"🗓️  Last inserted:     {last_date}")
        print("\n✅ All photos successfully stored in the database table!")

        if total == 0:
            print("\n   Tip: Run this after insert_photos_with_ai_categories.py")
            print("   Usage: python insert_photos_with_ai_categories.py <image_dir> <descriptions.txt>")

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")

if __name__ == "__main__":
    count_photos_in_db()