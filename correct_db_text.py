#!/usr/bin/env python3
"""
correct_db_text.py

Search and interactively correct text values in SQLite database tables.

Automatically detects likely text columns.
Uses rowid for safe updates.
Works even if 'filename' or 'id' columns are missing.

Usage:
  python correct_db_text.py image_collection.db "Jenny Agutter"
  python correct_db_text.py image_collection.db "Daily Life" image_comp
"""

import sqlite3
import sys


def connect(db_path: str) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Cannot open database {db_path}: {e}", file=sys.stderr)
        sys.exit(1)


def get_tables(cursor):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cursor.fetchall()]


def get_text_columns(cursor, table_name: str):
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    columns = [row[1] for row in cursor.fetchall()]

    keywords = ['title', 'description', 'subject', 'category', 'name', 'text', 'xml_title', 'xml_subject']
    likely = [col for col in columns if any(kw in col.lower() for kw in keywords)]

    if likely:
        return likely

    # fallback: first few non-BLOB columns
    non_blob = [c for c in columns if 'blob' not in c.lower() and c not in ('id', 'rowid')]
    return non_blob[:4] or columns[:4]


def search_text(conn: sqlite3.Connection, table: str, search_term: str):
    cursor = conn.cursor()
    columns = get_text_columns(cursor, table)

    if not columns:
        print(f"No columns found in table '{table}'")
        return []

    print(f"Searching table '{table}' in columns: {', '.join(columns)}")

    results = []

    for col in columns:
        query = f'''
            SELECT rowid          AS row_id,
                   "{col}"        AS search_value,
                   COALESCE(filename, '(no filename)') AS display_name
            FROM   "{table}"
            WHERE  "{col}" LIKE ?
            ORDER BY rowid
        '''

        print(f"  → Query for column '{col}':")
        print("   ", query.strip().replace('\n', '  '))

        try:
            cursor.execute(query, (f"%{search_term}%",))
            for row in cursor.fetchall():
                # Primary access via named keys
                try:
                    rowid = row['row_id']
                    value = row['search_value'] or '(empty)'
                    fname = row['display_name']
                except KeyError:
                    # Fallback to positional access
                    rowid = row[0]
                    value = row[1] or '(empty)'
                    fname = row[2]

                results.append((rowid, col, value, fname))

        except sqlite3.Error as e:
            print(f"  Failed querying column '{col}': {e}")

    return results


def print_results(results):
    if not results:
        print("\nNo matching rows found.")
        return

    print(f"\nFound {len(results)} matching row(s):\n")
    print(f"{'#':>2}  {'rowid':>6}  {'column':<16}  {'filename / preview':<38}  {'value'}")
    print("-" * 110)

    for i, (rid, col, val, fname) in enumerate(results, 1):
        val_short = str(val)[:65] + '…' if len(str(val)) > 65 else str(val)
        fname_short = str(fname)[:35] + '…' if len(str(fname)) > 35 else str(fname)
        print(f"{i:>2}  {rid:>6}  {col:<16}  {fname_short:<38}  {val_short}")

    print("-" * 110)


def update_row(conn: sqlite3.Connection, table: str, rowid: int, column: str, new_value: str):
    try:
        cursor = conn.cursor()
        cursor.execute(f'UPDATE "{table}" SET "{column}" = ? WHERE rowid = ?', (new_value, rowid))
        conn.commit()
        print(f"Updated rowid {rowid} in column '{column}' → {new_value}")
    except sqlite3.Error as e:
        print(f"Update failed: {e}")


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
        print(f"Table '{table_arg}' not found → using '{tables[0]}'")
        table = tables[0]

    print(f"→ Working on table: {table}\n")

    results = search_text(conn, table, search_term)

    print_results(results)

    while results:
        choice = input("\nEnter row # to edit (empty or q = quit): ").strip()
        if not choice or choice.lower() in ('q', 'quit'):
            break

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(results):
                print("Invalid row number.")
                continue

            rowid, col, old_val, fname = results[idx]

            print(f"\nEditing rowid {rowid} | column: {col} | file: {fname}")
            print(f"Current:\n  {old_val}")

            new_val = input("\nNew value (empty = skip): ").strip()
            if not new_val:
                print("No change.")
                continue

            confirm = input(f"\nApply change to:\n  {new_val}\n\n[y/N]: ").strip().lower()
            if confirm in ('y', 'yes'):
                update_row(conn, table, rowid, col, new_val)
            else:
                print("Cancelled.")

        except ValueError:
            print("Please enter a number.")
        except KeyboardInterrupt:
            print("\nAborted.")
            break

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()