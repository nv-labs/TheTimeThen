import sqlite3

conn = sqlite3.connect("universal_image_archive.db")
cur = conn.cursor()

cur.execute("DELETE FROM photos")
conn.commit()
conn.close()

print("photos table cleared")
