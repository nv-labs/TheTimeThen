import sqlite3
import os
import io
import sys
import random
import subprocess
from datetime import datetime
import textwrap
import shutil
import math

import numpy as np
import imageio
from PIL import Image, ImageDraw, ImageFont

# ================= CONFIG =================

BASE = os.path.dirname(os.path.abspath(__file__))

# CHANGED: Now using your image_collection database
DB = os.path.join(BASE, "image_collection.db")
TABLE = "image_comp"

# Column names in your image_comp table (adjust if different)
# Assuming your table has:
# - id (INTEGER PRIMARY KEY)
# - file_data (BLOB)          ← the image bytes
# - description (TEXT)        ← caption/text to show
# - VideoAirDate (TEXT)       ← we'll add/update this

ASSETS = os.path.join(BASE, "VideoAssets")

INTRO_IMAGE = os.path.join(ASSETS, "Logo.jpg")
OUTRO_IMAGE = os.path.join(ASSETS, "End Screen V2.png")

SONG_1 = os.path.join(ASSETS, "Andres Jacque - Skipping [Thematic].mp3")
SONG_2 = os.path.join(ASSETS, "Gymnopedie no1 - Satie.mp3")
OUTRO_MP4 = os.path.join(ASSETS, "Outro - The Time Then.mp4")

TARGET_TOTAL = 605        # Total desired video length in seconds
INTRO_SEC = 4
OUTRO_SEC = 12
IMAGE_SEC = 17            # Time each photo is shown

WIDTH, HEIGHT = 1920, 1088
FPS = 24

# =========================================


def ffmpeg_bin():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    win = r"C:\ffmpeg-8.0.1-essentials_build\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"
    if os.path.isfile(win):
        return win
    raise RuntimeError("ffmpeg not found")


def ensure_airdate_column(conn):
    """Add VideoAirDate column if it doesn't exist"""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({TABLE})")
    columns = [row[1] for row in cur.fetchall()]
    if "VideoAirDate" not in columns:
        print("ℹ️  Adding 'VideoAirDate' column to table...")
        cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN VideoAirDate TEXT")
        conn.commit()
        print("✅ VideoAirDate column added.")


# ---------- VISUALS ----------

def star_bg():
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    d = ImageDraw.Draw(img)
    for _ in range(200):
        x, y = random.randint(0, WIDTH), random.randint(0, HEIGHT)
        r = random.randint(1, 2)
        d.ellipse((x-r, y-r, x+r, y+r), fill="white")
    return img


def render_photo(blob, text):
    bg = star_bg()
    img = Image.open(io.BytesIO(blob)).convert("RGB")
    img.thumbnail((WIDTH * 0.9, HEIGHT * 0.9), Image.Resampling.LANCZOS)
    bg.paste(img, ((WIDTH - img.width) // 2, (HEIGHT - img.height) // 2))

    if text:
        try:
            font = ImageFont.truetype("arial.ttf", 42)
        except:
            font = ImageFont.load_default()

        lines = textwrap.wrap(text, 80)
        bar_h = len(lines) * 52 + 40
        bar = Image.new("RGBA", (WIDTH, bar_h), (0, 0, 0, 160))
        d = ImageDraw.Draw(bar)

        y = 20
        for ln in lines:
            w = d.textlength(ln, font=font)
            d.text(((WIDTH - w) // 2, y), ln, fill="white", font=font)
            y += 52

        bg = bg.convert("RGBA")
        bg.paste(bar, (0, HEIGHT - bar_h), bar)
        bg = bg.convert("RGB")

    return np.array(bg)


def static_frame(path):
    img = Image.open(path).convert("RGB")
    img.thumbnail((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    bg = star_bg()
    bg.paste(img, ((WIDTH - img.width) // 2, (HEIGHT - img.height) // 2))
    return np.array(bg)


# ---------- MAIN ----------

def main(outdir):
    ffmpeg = ffmpeg_bin()
    print(f"🎞️ ffmpeg: {ffmpeg}")

    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)

    if not os.path.exists(DB):
        print(f"❌ Database not found: {DB}")
        return

    conn = sqlite3.connect(DB)
    ensure_airdate_column(conn)  # Auto-add column if missing
    cur = conn.cursor()

    main_secs_target = TARGET_TOTAL - OUTRO_SEC
    images_needed = math.floor((main_secs_target - INTRO_SEC) / IMAGE_SEC)

    print(f"🎯 Target total: {TARGET_TOTAL}s")
    print(f"🖼️ Images needed: {images_needed}")

    # Select images that haven't been used yet (VideoAirDate IS NULL) first
    cur.execute(f"""
        SELECT id, file_data, description
        FROM {TABLE}
        ORDER BY
            CASE WHEN VideoAirDate IS NULL THEN 0 ELSE 1 END,
            VideoAirDate ASC,
            id ASC
        LIMIT ?
    """, (images_needed,))

    rows = cur.fetchall()
    if not rows:
        print("❌ No images found in the database.")
        conn.close()
        return

    print(f"✅ Selected {len(rows)} images for the video.")

    frames = []
    used_ids = []

    # INTRO
    frames += [static_frame(INTRO_IMAGE)] * int(INTRO_SEC * FPS)

    # MAIN PHOTOS
    for pid, blob, desc in rows:
        frame = render_photo(blob, desc)
        frames += [frame] * int(IMAGE_SEC * FPS)
        used_ids.append(pid)

    # OUTRO IMAGE (static)
    frames += [static_frame(OUTRO_IMAGE)] * int(OUTRO_SEC * FPS)

    # Calculate actual main duration
    main_video_duration = INTRO_SEC + len(rows) * IMAGE_SEC
    half_main = main_video_duration / 2

    print(f"📏 Actual main duration: {main_video_duration}s ({len(rows)} images)")
    print(f"➡️ First half: {half_main:.2f}s | Second half: {main_video_duration - half_main:.2f}s")

    temp_video = os.path.join(outdir, "video.mp4")
    imageio.mimsave(
        temp_video,
        frames,
        fps=FPS,
        codec="libx264",
        quality=8,
        macro_block_size=1
    )

    # ---------- AUDIO PROCESSING (same perfect sync as before) ----------

    a1 = os.path.join(outdir, "a1.wav")
    a2 = os.path.join(outdir, "a2.wav")
    a3 = os.path.join(outdir, "a3.wav")

    subprocess.run([
        ffmpeg, "-y",
        "-stream_loop", "-1", "-i", SONG_1,
        "-t", str(half_main),
        "-acodec", "pcm_s16le",
        a1
    ], check=True)

    subprocess.run([
        ffmpeg, "-y",
        "-stream_loop", "-1", "-i", SONG_2,
        "-t", str(main_video_duration - half_main),
        "-acodec", "pcm_s16le",
        a2
    ], check=True)

    subprocess.run([
        ffmpeg, "-y",
        "-i", OUTRO_MP4,
        "-vn", "-acodec", "pcm_s16le",
        "-t", str(OUTRO_SEC),
        "-ar", "44100", "-ac", "2",
        a3
    ], check=True)

    concat = os.path.join(outdir, "audio.txt")
    with open(concat, "w", encoding="utf-8") as f:
        for audio_file in [a1, a2, a3]:
            f.write(f"file '{os.path.abspath(audio_file)}'\n")

    final_audio = os.path.join(outdir, "audio.wav")
    subprocess.run([
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat,
        "-c", "copy",
        final_audio
    ], check=True)

    final_video = os.path.join(outdir, "slideshow.mp4")
    subprocess.run([
        ffmpeg, "-y",
        "-i", temp_video,
        "-i", final_audio,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        final_video
    ], check=True)

    # Cleanup temp files
    for f in [temp_video, a1, a2, a3, final_audio, concat]:
        if os.path.exists(f):
            os.remove(f)

    # Mark used images with current timestamp
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.executemany(
        f"UPDATE {TABLE} SET VideoAirDate = ? WHERE id = ?",
        [(stamp, pid) for pid in used_ids]
    )
    conn.commit()
    conn.close()

    print("\n🎬 VIDEO CREATED SUCCESSFULLY!")
    print(f"   Output: {final_video}")
    print(f"   Used {len(used_ids)} images from image_collection.db")
    print(f"   Marked them with VideoAirDate = {stamp}")
    print("✔ Perfect audio sync – no gaps, no drift!")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python VideoFromPhotosTable.py <output_directory>")
        sys.exit(1)
    main(sys.argv[1])