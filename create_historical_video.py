# create_historical_video.py
# Run this after you extracted photos with the previous script
# → Creates a stunning slideshow video with starry background + titles

import sqlite3
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import imageio
import random
from datetime import datetime

# ========================= CONFIG =========================
DB_NAME = 'universal_image_archive.db'
OUTPUT_DIR = r"C:\Users\Dell\dev\TheTimeThen\Output"  # ← change if you want
VIDEO_NAME = f"Historical_Photos_{datetime.now():%Y%m%d_%H%M}.mp4"

# Video settings (1080p with black bars = 1920x1088)
WIDTH, HEIGHT = 1920, 1088
FPS = 24
SECONDS_PER_PHOTO = 17   # matches your original style

# Background stars (same as your original script)
def add_stars(img, num=250, seed=None):
    if seed is not None: random.seed(seed)
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for _ in range(num):
        x, y = random.randint(0, w), random.randint(0, h)
        size = random.choice([1, 1, 1, 2])
        brightness = random.randint(100, 255)
        draw.ellipse((x-size, y-size, x+size, y+size), fill=(255, 255, 255, brightness))
    return img

# Title overlay (bottom black bar with white text)
def add_title_overlay(pil_img, title):
    draw = ImageDraw.Draw(pil_img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except:
        font = ImageFont.load_default()
    
    lines = []
    wrapped = title
    if len(title) > 70:
        wrapped = title[:67] + "..."
    lines.append(wrapped)
    
    bar_height = 140
    bar = Image.new('RGBA', (WIDTH, bar_height), (0, 0, 0, 180))
    draw_bar = ImageDraw.Draw(bar)
    
    y = 20
    for line in lines:
        bbox = draw_bar.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        draw_bar.text(((WIDTH - text_w) // 2, y), line, fill=(255, 255, 255), font=font)
        y += 60
    
    pil_img.paste(bar, (0, HEIGHT - bar_height), bar)
    return pil_img

# ===================== MAIN =====================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Get all extracted photos (latest first)
    cur.execute("SELECT xml_title, description, file_data FROM photos_searched WHERE source_url LIKE '%YouTube%' ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        print("No photos found in database!")
        return
    
    print(f"Found {len(rows)} photos → creating video...")
    
    frames = []
    
    for idx, (title, desc, blob) in enumerate(rows):
        print(f"Processing {idx+1}/{len(rows)}: {title}")
        
        # Load image from BLOB
        img = Image.open(io.BytesIO(blob)).convert("RGB")
        
        # Resize and center on black background
        bg = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        bg = add_stars(bg, seed=idx)  # different stars each time
        
        # Resize photo to fit nicely
        img_ratio = img.width / img.height
        target_h = int(HEIGHT * 0.78)
        target_w = int(target_h * img_ratio)
        if target_w > WIDTH * 0.9:
            target_w = int(WIDTH * 0.9)
            target_h = int(target_w / img_ratio)
        
        img_resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        paste_x = (WIDTH - target_w) // 2
        paste_y = (HEIGHT - target_h) // 2 - 40
        bg.paste(img_resized, (paste_x, paste_y))
        
        # Add title overlay
        bg = add_title_overlay(bg, title)
        
        # Convert to numpy and add frames
        frame_np = np.array(bg)
        frames.extend([frame_np] * (SECONDS_PER_PHOTO * FPS))
    
    # Save video
    output_path = os.path.join(OUTPUT_DIR, VIDEO_NAME)
    imageio.mimsave(output_path, frames, fps=FPS, codec='libx264', quality=9)
    
    print(f"\nSUCCESS! Video created:")
    print(f"   → {output_path}")
    print(f"   → {len(rows)} photos, {len(frames)//FPS} seconds long")
    print(f"   → Ready for YouTube!")

if __name__ == "__main__":
    import io
    main()