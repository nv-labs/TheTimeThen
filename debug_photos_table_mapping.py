import sqlite3
import os
import io
from PIL import Image

DB_NAME = "universal_image_archive.db"
TABLE = "photos"

OUT_DIR = "debug_table_dump"
os.makedirs(OUT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()

cur.execute(f"""
    SELECT id, filename, description, file_data
    FROM {TABLE}
    ORDER BY id
""")

rows = cur.fetchall()

print(f"Dumping {len(rows)} rows...\n")

for pid, filename, description, blob in rows:
    # Save image
    img = Image.open(io.BytesIO(blob)).convert("RGB")
    img_name = f"{pid:05d}.jpg"
    img_path = os.path.join(OUT_DIR, img_name)
    img.save(img_path, "JPEG", quality=95)

    # Save text
    txt_path = os.path.join(OUT_DIR, f"{pid:05d}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"ID: {pid}\n")
        f.write(f"Filename: {filename}\n\n")
        f.write(description or "[NO DESCRIPTION]")

    print(f"ID {pid} → {img_name}")

conn.close()

print("\n✅ Done.")
print("Open the folder:", os.path.abspath(OUT_DIR))
