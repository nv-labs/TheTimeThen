import os
import sqlite3
import sys

# ================= CONFIG =================
DB_NAME = "image_collection.db"
TABLE_NAME = "image_comp"  # Same table as insert_photos_with_ai_categories.py
# =========================================


def connect_to_db():
    if not os.path.exists(DB_NAME):
        print(f"❌ Database file '{DB_NAME}' not found.")
        sys.exit(1)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Check if the required table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,))
    if cursor.fetchone() is None:
        print(f"❌ Table '{TABLE_NAME}' does not exist in '{DB_NAME}'.")
        sys.exit(1)

    print(f"✅ Connected to database '{DB_NAME}' → table '{TABLE_NAME}'")
    return conn


def find_and_remove_duplicates(dry_run=False):
    conn = connect_to_db()
    cursor = conn.cursor()

    # Find duplicates: filenames that appear more than once
    cursor.execute(f"""
        SELECT filename, COUNT(*) as count, GROUP_CONCAT(id) as ids
        FROM {TABLE_NAME}
        GROUP BY filename
        HAVING count > 1
        ORDER BY count DESC
    """)

    duplicates = cursor.fetchall()

    if not duplicates:
        print("✅ No duplicates found!")
        conn.close()
        return

    print(f"🔍 Found {len(duplicates)} duplicate filename(s):\n")

    total_to_remove = 0

    for filename, count, ids in duplicates:
        id_list = ids.split(",")
        print(f"  • {filename}: {count} copies (IDs: {ids})")
        total_to_remove += count - 1  # Keep 1, remove the rest

    print(f"\n📊 Total records to remove: {total_to_remove}")

    if dry_run:
        print("\n🔍 DRY RUN MODE — No changes made")
        conn.close()
        return

    # Confirm before deletion
    confirm = input("\n⚠️  Remove duplicates? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("❌ Cancelled.")
        conn.close()
        return

    # Remove duplicates: keep the first occurrence, delete the rest
    removed_count = 0
    for filename, count, ids in duplicates:
        id_list = [int(id) for id in ids.split(",")]
        id_list.sort()  # Keep the first (lowest) ID
        ids_to_delete = id_list[1:]  # Remove the rest

        for id_to_delete in ids_to_delete:
            cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = ?", (id_to_delete,))
            removed_count += 1

    conn.commit()
    print(f"\n✅ Removed {removed_count} duplicate record(s)")
    conn.close()


def main():
    dry_run = False
    if "-dry-run" in sys.argv or "--dry-run" in sys.argv:
        dry_run = True
        print("🔍 Running in DRY RUN mode (no changes will be made)\n")

    find_and_remove_duplicates(dry_run=dry_run)
    print(f"\n🎉 Done!")


if __name__ == "__main__":
    main()
