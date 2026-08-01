import sqlite3

DATABASE = 'universal_image_archive.db'

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

# Delete all rows added in the last 2 hours
cursor.execute("""
    DELETE FROM archived_files
    WHERE added_date >= DATETIME('now', '-0.2 hours')
""")

deleted_count = cursor.rowcount
conn.commit()
conn.close()

print(f"Deleted {deleted_count} records added in the last 2 hours.")
