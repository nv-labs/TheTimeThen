#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('image_collection.db')
cur = conn.cursor()

# Count Exploration images
cur.execute("SELECT COUNT(*) FROM image_comp WHERE xml_subject = 'Exploration'")
exploration_count = cur.fetchone()[0]

print(f"✅ Exploration images: {exploration_count}")
print(f"\n📊 For 20-minute video:")
print(f"   Need: 85 images (14 sec each)")
print(f"   Available: {exploration_count}")

if exploration_count >= 85:
    print(f"   Status: ✅ ENOUGH! ({exploration_count - 85} extra)")
else:
    print(f"   Status: ❌ NOT ENOUGH! (short by {85 - exploration_count})")

# Show all categories with counts
print(f"\n📂 All categories:")
categories = [
    "Actors", "Politicians", "Military", "Historical Events", 
    "Places", "Cities", "Architecture", "Sports", "Science", 
    "Technology", "Exploration", "Royalty", "Art", "Culture", 
    "Everyday Life"
]

for cat in categories:
    cur.execute("SELECT COUNT(*) FROM image_comp WHERE xml_subject = ?", (cat,))
    count = cur.fetchone()[0]
    status = "✅" if count >= 85 else "⚠️ "
    print(f"   {status} {cat:20} : {count:4} images")

conn.close()
