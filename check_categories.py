#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('image_collection.db')
cur = conn.cursor()

# Check columns
cur.execute("PRAGMA table_info(image_comp)")
cols = [(r[1], r[2]) for r in cur.fetchall()]
print("Columns in image_comp:")
for col, dtype in cols:
    print(f"  - {col} ({dtype})")

# Check xml_subject unique values
print("\n" + "="*70)
print("Categories in xml_subject column:")
print("="*70)
cur.execute("SELECT xml_subject, COUNT(*) as count FROM image_comp GROUP BY xml_subject ORDER BY count DESC")
for cat, count in cur.fetchall():
    print(f"  {cat:30} : {count:4} images")

# Total
cur.execute("SELECT COUNT(*) FROM image_comp")
total = cur.fetchone()[0]
print(f"\n{'Total images':30} : {total:4}")

conn.close()
