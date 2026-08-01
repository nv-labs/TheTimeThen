import sqlite3

# 1. Connect to the database file
conn = sqlite3.connect("universal_image_archive.db")

# 2. Create a cursor (used to run SQL commands)
cur = conn.cursor()

# 3. Delete all rows from the table
cur.execute("DELETE FROM photos_searched")

# 4. Save changes
conn.commit()

# 5. Optional but recommended: reclaim disk space
conn.execute("VACUUM")

# 6. Close the connection
conn.close()

print("✅ All images deleted from photos_searched")