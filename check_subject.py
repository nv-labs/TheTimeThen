#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('image_collection.db')
cur = conn.cursor()

# Check first few xml_subject values
print("Sample xml_subject values:")
cur.execute("SELECT DISTINCT xml_subject FROM image_comp LIMIT 20")
for row in cur.fetchall():
    print(f"  - {row[0]}")

conn.close()
