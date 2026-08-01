import sqlite3
db_name = 'image_collection.db'
table_name = 'image_comp'
conn = sqlite3.connect(db_name)
cursor = conn.cursor()

# Check if table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
if not cursor.fetchone():
    print(f'Table {table_name} does not exist')
    conn.close()
    exit(1)

# Get row count
cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
count = cursor.fetchone()[0]
print(f'Total rows in {table_name}: {count}')

# Check a few entries
cursor.execute(f'SELECT id, filename FROM {table_name} LIMIT 5')
rows = cursor.fetchall()
print(f'\nFirst 5 entries:')
for row_id, filename in rows:
    print(f'  id={row_id}, filename={filename}')

conn.close()
