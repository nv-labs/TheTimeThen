import os
import sys
import sqlite3
from datetime import datetime

# ================= CONFIG =================
DB_NAME = "image_collection.db"
TABLE_NAME = "image_comp"   # Must match the table used by insert_photos_with_ai_categories.py
# =========================================


def connect_to_db():
    if not os.path.exists(DB_NAME):
        print(f"❌ Database file '{DB_NAME}' not found.")
        print("   Make sure you are in the same folder as image_collection.db")
        sys.exit(1)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Verify the table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,))
    if cursor.fetchone() is None:
        print(f"❌ Table '{TABLE_NAME}' does not exist in '{DB_NAME}'.")
        sys.exit(1)

    print(f"✅ Connected to database '{DB_NAME}' → table '{TABLE_NAME}'")
    return conn


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("   python delete_photos_by_date.py YYYY-MM-DD")
        print("\nExample for February 24th 2026:")
        print("   python delete_photos_by_date.py 2026-02-24")
        sys.exit(1)

    date_str = sys.argv[1].strip()

    # Validate date format
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print("❌ Invalid date format! Use YYYY-MM-DD (e.g. 2026-02-24)")
        sys.exit(1)

    conn = connect_to_db()
    cursor = conn.cursor()

    # === STEP 1: Count how many photos would be deleted ===
    cursor.execute(f"""
        SELECT COUNT(*) 
        FROM {TABLE_NAME} 
        WHERE DATE(added_date) = ?
    """, (date_str,))

    count = cursor.fetchone()[0]

    if count == 0:
        print(f"✅ No photos were inserted on {date_str}.")
        conn.close()
        sys.exit(0)

    print(f"\n⚠️  Found {count} photo(s) inserted on {date_str}")

    # Show a few sample filenames so the user can double-check
    cursor.execute(f"""
        SELECT filename 
        FROM {TABLE_NAME} 
        WHERE DATE(added_date) = ? 
        LIMIT 10
    """, (date_str,))
    
    samples = cursor.fetchall()
    if samples:
        print("   Sample filenames that will be deleted:")
        for row in samples:
            print(f"     • {row[0]}")

    # === STEP 2: Ask for confirmation ===
    print("\n" + "="*60)
    confirm = input(f"❗ DELETE ALL {count} photos from {date_str}?\n"
                    "   This action CANNOT be undone!\n\n"
                    "   Type YES (in uppercase) to confirm: ").strip()

    if confirm != "YES":
        print("❌ Deletion cancelled by user.")
        conn.close()
        sys.exit(0)

    # === STEP 3: Perform the deletion ===
    try:
        cursor.execute(f"""
            DELETE FROM {TABLE_NAME} 
            WHERE DATE(added_date) = ?
        """, (date_str,))

        deleted = cursor.rowcount
        conn.commit()

        print(f"\n🎉 SUCCESS — Deleted {deleted} photo(s) inserted on {date_str}")
        
    except sqlite3.Error as e:
        print(f"❌ Database error during deletion: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    main()