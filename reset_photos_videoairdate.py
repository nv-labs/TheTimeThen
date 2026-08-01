import sqlite3

DB_NAME = "universal_image_archive.db"
TABLE = "photos"

def reset_videoairdate():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Ensure table exists
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE,)
    )
    if not cur.fetchone():
        raise RuntimeError(f"Table not found: {TABLE}")

    # Ensure column exists
    cur.execute(f"PRAGMA table_info({TABLE})")
    cols = [c[1] for c in cur.fetchall()]
    if "VideoAirDate" not in cols:
        raise RuntimeError("Column VideoAirDate not found in photos table")

    # Reset VideoAirDate
    cur.execute(f"UPDATE {TABLE} SET VideoAirDate = NULL")
    conn.commit()
    conn.close()

    print("✅ VideoAirDate reset to NULL for table: photos")

if __name__ == "__main__":
    reset_videoairdate()
