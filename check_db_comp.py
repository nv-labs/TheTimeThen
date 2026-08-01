import sqlite3
import os

DB = "image_collection.db"
TABLE = "image_comp"
LIMIT = 200   # change this number if you want more rows

if not os.path.exists(DB):
    print(f"❌ Database not found: {DB}")
    exit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Show column names
cur.execute(f"PRAGMA table_info({TABLE})")
columns = [col[1] for col in cur.fetchall()]
print("📋 Columns:", columns)

print("\n📄 Sample rows:\n")

cur.execute(f"""
    SELECT id, filename, description, VideoAirDate
    FROM {TABLE}
    ORDER BY id
    LIMIT ?
""", (LIMIT,))

rows = cur.fetchall()

for row in rows:
    print(row)

conn.close()
