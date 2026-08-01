#!/usr/bin/env python3
"""
delete_photo_by_text.py

Search text values in SQLite database tables, then interactively delete the
associated photo row after explicit confirmation.

Usage:
  python delete_photo_by_text.py image_collection.db "Jenny Agutter"
  python delete_photo_by_text.py image_collection.db "Daily Life" image_comp
"""

import sqlite3
import sys


def connect(db_path: str) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as error:
        print(f"Cannot open database {db_path}: {error}", file=sys.stderr)
        sys.exit(1)


def get_tables(cursor):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cursor.fetchall()]


def get_columns(cursor, table_name: str):
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return [row[1] for row in cursor.fetchall()]


def get_text_columns(cursor, table_name: str):
    columns = get_columns(cursor, table_name)

    keywords = [
        "title",
        "description",
        "subject",
        "category",
        "name",
        "text",
        "xml_title",
        "xml_subject",
        "filename",
    ]
    likely = [col for col in columns if any(kw in col.lower() for kw in keywords)]

    if likely:
        return likely

    non_blob = [c for c in columns if "blob" not in c.lower() and c not in ("id", "rowid")]
    return non_blob[:4] or columns[:4]


def get_display_identifier(available_columns):
    preferred = ["filename", "file_name", "path", "image_path", "name", "title"]
    for col in preferred:
        if col in available_columns:
            return col
    return None


def search_text(conn: sqlite3.Connection, table: str, search_term: str):
    cursor = conn.cursor()
    table_columns = get_columns(cursor, table)
    text_columns = get_text_columns(cursor, table)

    if not text_columns:
        print(f"No columns found in table '{table}'")
        return []

    display_col = get_display_identifier(table_columns)
    display_expr = f'"{display_col}"' if display_col else "NULL"

    print(f"Searching table '{table}' in columns: {', '.join(text_columns)}")

    by_row = {}

    for col in text_columns:
        query = f'''
            SELECT rowid AS row_id,
                   "{col}" AS search_value,
                   {display_expr} AS display_name
            FROM "{table}"
            WHERE "{col}" LIKE ?
            ORDER BY rowid
        '''

        try:
            cursor.execute(query, (f"%{search_term}%",))
            for row in cursor.fetchall():
                rowid = row["row_id"]
                value = row["search_value"] or "(empty)"
                display_name = row["display_name"] or "(no identifier)"
                if rowid not in by_row:
                    by_row[rowid] = {"identifier": "(no identifier)", "matches": []}
                by_row[rowid]["identifier"] = display_name
                by_row[rowid]["matches"].append({"column": col, "value": str(value)})
        except sqlite3.Error as error:
            print(f"Failed querying column '{col}': {error}")

    results = []
    for rowid in sorted(by_row.keys()):
        results.append(
            {
                "rowid": rowid,
                "identifier": by_row[rowid]["identifier"],
                "matches": by_row[rowid]["matches"],
            }
        )

    return results


def print_results(results):
    if not results:
        print("\nNo matching rows found.")
        return

    print(f"\nFound {len(results)} matching photo row(s):\n")
    print(f"{'#':>2}  {'rowid':>6}  {'photo identifier':<45}  {'matched columns'}")
    print("-" * 110)

    for i, item in enumerate(results, 1):
        identifier = str(item["identifier"])
        identifier_short = identifier[:42] + "..." if len(identifier) > 45 else identifier
        columns = ", ".join(sorted({m["column"] for m in item["matches"]}))
        print(f"{i:>2}  {item['rowid']:>6}  {identifier_short:<45}  {columns}")
        # Show all matched column values for this result
        for match in item["matches"]:
            value = match["value"]
            value_short = value[:120] + "..." if len(value) > 120 else value
            print(f"      - {match['column']}: {value_short}")
        print()
    print("-" * 110)


def print_exact_photo(item):
    print("\nExact photo candidate:")
    print(f"  rowid: {item['rowid']}")
    print(f"  identifier: {item['identifier']}")
    print("  matched values:")
    for match in item["matches"]:
        value = match["value"]
        value_short = value[:120] + "..." if len(value) > 120 else value
        print(f"    - {match['column']}: {value_short}")


def delete_row(conn: sqlite3.Connection, table: str, rowid: int):
    try:
        cursor = conn.cursor()
        cursor.execute(f'DELETE FROM "{table}" WHERE rowid = ?', (rowid,))
        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as error:
        print(f"Delete failed: {error}")
        return 0


def confirmation_required(item):
    print_exact_photo(item)

    confirm = input("\nDelete this photo row? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Cancelled.")
        return False

    return True


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    db_path = sys.argv[1]
    search_term = sys.argv[2].strip()
    table_arg = sys.argv[3] if len(sys.argv) >= 4 else None

    conn = connect(db_path)
    cursor = conn.cursor()

    tables = get_tables(cursor)
    if not tables:
        print("No user tables found in database.")
        conn.close()
        sys.exit(1)

    print(f"Database: {db_path}")
    print(f"Available tables: {', '.join(tables)}")

    table = table_arg or tables[0]
    if table_arg and table_arg not in tables:
        print(f"Table '{table_arg}' not found, using '{tables[0]}'")
        table = tables[0]

    print(f"Working on table: {table}\n")

    results = search_text(conn, table, search_term)
    print_results(results)

    while results:
        choice = input("\nEnter row # to delete (empty or q = quit): ").strip()
        if not choice or choice.lower() in ("q", "quit"):
            break

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(results):
                print("Invalid row number.")
                continue

            selected = results[idx]

            if not confirmation_required(selected):
                continue

            deleted = delete_row(conn, table, selected["rowid"])
            if deleted:
                print(f"Deleted rowid {selected['rowid']} from table '{table}'.")
                results.pop(idx)
                if results:
                    print_results(results)
                else:
                    print("No remaining matches.")
            else:
                print("No row deleted.")

        except ValueError:
            print("Please enter a number.")
        except KeyboardInterrupt:
            print("\nAborted.")
            break

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
