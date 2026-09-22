# check_db_photos.py
import glob
import os
import sqlite3

DB_DIR = r"D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\databases"
PREFERRED_TABLES = ("photos", "image_comp")
AIR_DATE_CANDIDATES = ("VideoAirDate", "video_air_date", "air_date")
CATEGORY_CANDIDATES = {
    "photos": ("category", "xml_subject"),
    "image_comp": ("xml_subject", "category"),
}
DATE_CANDIDATES = ("added_date", "addedDate", "date_added")
CHUNK_SIZE = 1000


def get_db_files():
    if not os.path.isdir(DB_DIR):
        print(f"Database folder not found: {DB_DIR}")
        return []

    db_files = sorted(glob.glob(os.path.join(DB_DIR, "*.db")))
    if not db_files:
        print(f"No .db files found in: {DB_DIR}")
    return db_files


def table_exists(cursor, table_name):
    try:
        cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
        cursor.fetchone()
        return True
    except sqlite3.Error:
        return False


def get_table_name(cursor):
    for table_name in PREFERRED_TABLES:
        if table_exists(cursor, table_name):
            return table_name
    return None


def get_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def pick_first(existing_columns, candidates):
    for name in candidates:
        if name in existing_columns:
            return name
    return None


def scan_stats(cursor, table_name, columns):
    category_col = pick_first(columns, CATEGORY_CANDIDATES.get(table_name, ("category", "xml_subject")))
    date_col = pick_first(columns, DATE_CANDIDATES)
    air_date_col = pick_first(columns, AIR_DATE_CANDIDATES)

    total = cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    max_id_row = cursor.execute(f"SELECT MAX(id) FROM {table_name}").fetchone()
    max_id = max_id_row[0] if max_id_row and max_id_row[0] else 0

    seen = set()
    first_date = None
    last_date = None
    null_air_dates = 0 if air_date_col else None

    select_parts = ["id"]
    if category_col:
        select_parts.append(category_col)
    if date_col:
        select_parts.append(date_col)
    if air_date_col:
        select_parts.append(air_date_col)
    select_sql = f"SELECT {", ".join(select_parts)} FROM {table_name} WHERE id BETWEEN ? AND ?"

    for start in range(1, max_id + 1, CHUNK_SIZE):
        end = min(max_id, start + CHUNK_SIZE - 1)
        try:
            cursor.execute(select_sql, (start, end))
            rows = cursor.fetchall()
        except sqlite3.Error:
            continue

        for row in rows:
            offset = 1
            if category_col:
                value = row[offset]
                if value is not None and str(value).strip() != "":
                    seen.add(value)
                offset += 1
            if date_col:
                value = row[offset]
                if value is not None and str(value).strip() != "":
                    if first_date is None or value < first_date:
                        first_date = value
                    if last_date is None or value > last_date:
                        last_date = value
                offset += 1
            if air_date_col:
                value = row[offset]
                if value is None or str(value).strip() == "":
                    null_air_dates += 1

    return total, category_col, len(seen) if category_col else None, date_col, first_date or "N/A", last_date or "N/A", air_date_col, null_air_dates


def count_photos_in_db(db_path):
    print()
    print(f"Checking database: {db_path}")

    if not os.path.exists(db_path):
        print(f"   File missing: {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        table_name = get_table_name(cursor)
        if not table_name:
            print("   No supported table found (photos/image_comp).")
            conn.close()
            return

        columns = get_columns(cursor, table_name)
        total, category_col, category_count, date_col, first_date, last_date, air_date_col, null_air_dates = scan_stats(cursor, table_name, columns)
        conn.close()

        print(f"   Table:             {table_name}")
        print(f"   Total photos:      {total}")
        if category_col:
            print(f"   Unique categories: {category_count} ({category_col})")
        else:
            print("   Unique categories: N/A")
        if date_col:
            print(f"   First inserted:    {first_date}")
            print(f"   Last inserted:     {last_date}")
        else:
            print("   Insert date column: N/A")
        if air_date_col:
            print(f"   Null/empty {air_date_col}: {null_air_dates}")
        else:
            print("   Air date column not found")

    except sqlite3.Error as e:
        print(f"   Database error: {e}")


def main():
    db_files = get_db_files()
    if not db_files:
        return

    for db_path in db_files:
        count_photos_in_db(db_path)

    print()
    print("Finished checking all databases in:")
    print(DB_DIR)


if __name__ == "__main__":
    main()
