import sqlite3
conn = sqlite3.connect('image_collection.db')
cur = conn.cursor()
rows = list(cur.execute('PRAGMA table_info(image_comp)'))
print(rows)
conn.close()