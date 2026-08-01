# view_in_browser.py
import sqlite3
import base64
import webbrowser
import os

DB = 'universal_image_archive.db'
TABLE = 'photos_searched'

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute(f"SELECT filename, file_data, xml_title, description FROM {TABLE} ORDER BY id DESC")
rows = cur.fetchall()

html = """
<!DOCTYPE html>
<html><head><title>1970 USA Events - Photos</title>
<style>
  body { font-family: Arial; margin: 40px; background: #f4f4f4; }
  .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
  .card { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
  img { max-width: 100%; height: auto; border-radius: 8px; }
  h3 { margin: 10px 0 5px; color: #333; }
  p { margin: 5px 0; color: #666; font-size: 0.9em; }
</style>
</head><body>
<h1>1970 USA Events - Photo Gallery</h1>
<div class="gallery">
"""

for fn, data, title, desc in rows:
    b64 = base64.b64encode(data).decode()
    ext = os.path.splitext(fn)[1].lower()
    mime = "image/jpeg" if ext in ['.jpg','.jpeg'] else "image/png" if ext == '.png' else "image/gif"
    html += f"""
    <div class="card">
        <img src="data:{mime};base64,{b64}" alt="{title}">
        <h3>{title}</h3>
        <p>{desc}</p>
    </div>
    """

html += "</div></body></html>"

with open("gallery.html", "w", encoding="utf-8") as f:
    f.write(html)

webbrowser.open("gallery.html")
print("Gallery opened in browser!")