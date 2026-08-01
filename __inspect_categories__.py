import sqlite3
conn = sqlite3.connect('image_collection.db')
cur = conn.cursor()
rows = list(cur.execute('SELECT xml_subject, COUNT(*) FROM image_comp GROUP BY xml_subject ORDER BY COUNT(*) DESC LIMIT 20'))
for row in rows:
    print(row)
conn.close()