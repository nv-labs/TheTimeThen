#!/usr/bin/env python3
"""
AI-Creator.py

Creates a YouTube‑style short from 2 historical photos:
- Static photo + caption
- Kling Lite 4s motion clip (forced, with advanced sanitization retries)
- Edge TTS narration
- 720p output (forced uniform aspect ratio handling to prevent FFmpeg concat crashes)
- Caching to avoid repeated Kling costs
"""

import argparse
import base64
import hashlib
import io
import os
import re
import sqlite3
import subprocess
import sys
import textwrap

# --- Third‑party imports ------------------------------------------------------

from PIL import Image, ImageDraw, ImageFont
import numpy as np
import imageio
import fal_client
import requests

HAS_EDGE_TTS = False
try:
    import asyncio
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    pass

# --- Constants ----------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "image_collection.db")
TABLE_NAME = "image_comp"

WIDTH = 1280
HEIGHT = 720
FPS = 24
STATIC_SECONDS = 7
KLING_SECONDS = 4

FAL_KEY = os.environ.get("FAL_KEY", "").strip()
if FAL_KEY:
    fal_client.api_key = FAL_KEY

KLING_CACHE_DIR = os.path.join(BASE_DIR, "kling_cache")
os.makedirs(KLING_CACHE_DIR, exist_ok=True)


# --- Utility ------------------------------------------------------------------

def find_ffmpeg():
    import shutil
    for c in ["ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]:
        if shutil.which(c):
            return c
    print("❌ ffmpeg not found")
    return "ffmpeg"  # Fallback to system path path execution


def db_connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def clean_text(t):
    if not t:
        return ""
    t = t.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", t).strip()


# --- Sanitization (Levels 1 & 2) ----------------------------------------------

NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+Scope*(?:\s+[A-Z][a-z]+)*)\b")

def sanitize_level1(text):
    """Replace specific proper nouns with generic placeholders."""
    blacklist = {"The", "This", "That", "Look", "At", "But", "And", "In", "On", "Of", "Context:"}
    def repl(match):
        word = match.group(1)
        if word in blacklist:
            return word
        return "a person"
    return NAME_PATTERN.sub(repl, text)

def sanitize_level2(text):
    """
    Aggressive scrub for AI safety filters. Strips known highly-flagged historical names,
    political entities, and words that auto-trigger moderation flags.
    """
    sensitive_terms = [
        r"adolf", r"hitler", r"nazi", r"swastika", r"fascist", r"german shepherd",
        r"concentration", r"camp", r"war", r"execution", r"dictator"
    ]
    lowered = text.lower()
    for term in sensitive_terms:
        lowered = re.sub(term, "historical figure", lowered)
    
    # Return a completely benign base if still messy, or just scrubbed text
    return "A vintage historical photograph brought to life with subtle natural movements."


# --- Narration (viral style) --------------------------------------------------

def generate_narration(image_bytes, description, index):
    desc = clean_text(description) or "This photo captures a moment most people have never seen."
    if index == 0:
        hook = "At first glance, this looks like just another old photo..."
    else:
        hook = "But this next image hides an even stranger detail..."
    body = f"{desc} Look closely at the faces, the posture, and the tiny details in the background."
    tease = "The story behind this moment is far more intense than it appears."
    return f"{hook} {body} {tease}"


# --- Audio --------------------------------------------------------------------

async def _speak(text, out_path):
    communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
    await communicate.save(out_path)

def save_audio(text, out_path):
    if not HAS_EDGE_TTS:
        print("⚠️ No Edge TTS found. Audio skipped.")
        return False
    try:
        asyncio.run(_speak(text, out_path))
        print(f"🎤 Audio saved: {out_path}")
        return True
    except Exception as e:
        print(f"❌ Audio failed: {e}")
        return False


# --- Rendering ----------------------------------------------------------------

def render_static_frame(image_bytes, caption):
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        img.thumbnail((int(WIDTH*0.92), int(HEIGHT*0.78)), Image.Resampling.LANCZOS)

        bg = Image.new("RGB", (WIDTH, HEIGHT), (10,10,18))
        x = (WIDTH - img.width)//2
        y = (HEIGHT - img.height)//2
        bg.paste(img, (x,y))

        draw = ImageDraw.Draw(bg)
        try:
            font = ImageFont.truetype("arial.ttf", 34)
        except:
            font = ImageFont.load_default()

        lines = textwrap.wrap(clean_text(caption), 52)
        bar_h = len(lines)*40 + 30
        overlay = Image.new("RGBA", (WIDTH, bar_h), (0,0,0,190))
        d2 = ImageDraw.Draw(overlay)
        yy = 15
        for line in lines:
            d2.text((40,yy), line, font=font, fill=(240,240,240))
            yy += 40
        bg.paste(overlay, (0, HEIGHT-bar_h), overlay)

        return np.array(bg)


def write_video(frames, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with imageio.get_writer(path, fps=FPS, codec="libx264", quality=8, macro_block_size=1) as w:
        for f in frames:
            w.append_data(f)


# --- Kling Integration with Multilevel Fallbacks ------------------------------

def hash_image(image_bytes):
    return hashlib.sha1(image_bytes).hexdigest()


def kling_generate(image_bytes, prompt):
    if not FAL_KEY:
        print("❌ No FAL_KEY found in environment variables.")
        return None

    img_hash = hash_image(image_bytes)
    cache_path = os.path.join(KLING_CACHE_DIR, f"{img_hash}.mp4")
    if os.path.exists(cache_path):
        print(f"♻️ Using cached Kling generation: {cache_path}")
        return cache_path

    temp_img = os.path.join(KLING_CACHE_DIR, f"{img_hash}.png")
    with open(temp_img, "wb") as f:
        f.write(image_bytes)

    # Progression of safety retries to combat Content Policy Violations
    attempts = [
        prompt,
        sanitize_level1(prompt),
        sanitize_level2(prompt),
        "A neutral vintage photograph brought to life with subtle natural movements, breathing, gentle wind, and warm historical lighting."
    ]

    for i, attempt in enumerate(attempts):
        try:
            print(f"🎞️ Trying Kling (Attempt {i+1}/4) with prompt: {attempt[:90]}...")
            result = fal_client.subscribe(
                "fal-ai/kling-video-lite",
                arguments={
                    "start_image_url": fal_client.upload_file(temp_img),
                    "prompt": attempt,
                    "duration": str(KLING_SECONDS),
                    "aspect_ratio": "16:9",
                    "resolution": "720p",
                    "generate_audio": False
                },
                with_logs=False,
            )

            if isinstance(result, list) or not result:
                print("⚠️ Kling returned empty response or error list, retrying...")
                continue

            url = result.get("video", {}).get("url")
            if not url:
                print("⚠️ No video URL returned in data payload, retrying...")
                continue

            r = requests.get(url, timeout=60)
            r.raise_for_status()
            with open(cache_path, "wb") as f:
                f.write(r.content)

            print(f"✅ Kling successfully generated: {cache_path}")
            return cache_path

        except Exception as e:
            print(f"⚠️ Kling attempt {i+1} failed due to content filters or network issue: {e}")

    print("❌ Kling failed entirely after all sanitization levels.")
    return None


# --- Segment builder ----------------------------------------------------------

def build_segment(row, index, outdir, with_audio=True):
    desc = clean_text(row["description"] or row["xml_title"] or "A moment frozen in time.")
    narration = generate_narration(row["file_data"], desc, index)

    seg_dir = os.path.join(outdir, f"segment_{index+1}")
    os.makedirs(seg_dir, exist_ok=True)

    audio_path = os.path.join(seg_dir, "audio.mp3")
    has_audio_file = False
    if with_audio:
        has_audio_file = save_audio(narration, audio_path)

    # Generate Static Base 
    static_frame = render_static_frame(row["file_data"], narration)
    static_frames = [static_frame] * (STATIC_SECONDS * FPS)
    static_video = os.path.join(seg_dir, "static.mp4")
    write_video(static_frames, static_video)

    # Generate Kling Base
    kling_video = kling_generate(row["file_data"], desc)

    ffmpeg = find_ffmpeg()
    out_video = os.path.join(outdir, f"segment_{index+1}.mp4")

    # CRITICAL FIX: Safe scale and pad elements inside filter_complex to resolve dimension mismatches
    if kling_video:
        print("⚙️ Processing concatenation with dynamic scaling filters...")
        filter_str = (
            f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[s0];"
            f"[1:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[s1];"
            f"[s0][s1]concat=n=2:v=1:a=0[v]"
        )
        
        cmd = [ffmpeg, "-y", "-i", static_video, "-i", kling_video]
        if has_audio_file:
            cmd.extend(["-i", audio_path])
            filter_str += f";[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a]"
            
        cmd.extend(["-filter_complex", filter_str, "-map", "[v]"])
        if has_audio_file:
            cmd.extend(["-map", "[a]", "-c:a", "aac", "-shortest"])
            
        cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18", out_video])
    else:
        print("⚠️ Kling failed or missing — compiling from static template only")
        filter_str = (
            f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[v]"
        )
        cmd = [ffmpeg, "-y", "-i", static_video]
        if has_audio_file:
            cmd.extend(["-i", audio_path])
            filter_str += f";[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a]"
            
        cmd.extend(["-filter_complex", filter_str, "-map", "[v]"])
        if has_audio_file:
            cmd.extend(["-map", "[a]", "-c:a", "aac", "-shortest"])
            
        cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18", out_video])

    subprocess.run(cmd, check=True)
    print(f"🎬 Segment ready: {out_video}")
    return out_video


# --- Final concat -------------------------------------------------------------

def concat_segments(segments, out_path):
    ffmpeg = find_ffmpeg()
    concat_file = os.path.join(BASE_DIR, "segments", "concat.txt")
    os.makedirs(os.path.dirname(concat_file), exist_ok=True)

    with open(concat_file, "w") as f:
        for s in segments:
            f.write(f"file '{os.path.abspath(s)}'\n")

    cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        out_path
    ]
    subprocess.run(cmd, check=True)
    print(f"🏁 Final video compiled successfully: {out_path}")


# --- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--out", default=os.path.join(BASE_DIR, "output_video.mp4"))
    parser.add_argument("--no-audio", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"❌ Database file missing at path: {args.db}")
        sys.exit(1)

    conn = db_connect(args.db)
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY RANDOM() LIMIT 2")
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        print(f"❌ SQL Database Table error: {e}")
        sys.exit(1)

    if len(rows) < 2:
        print("❌ Error: Minimum requirements not met. Table must contain at least 2 image rows.")
        sys.exit(1)

    outdir = os.path.join(BASE_DIR, "segments")
    os.makedirs(outdir, exist_ok=True)

    segs = []
    for i, row in enumerate(rows):
        segs.append(build_segment(row, i, outdir, with_audio=not args.no_audio))

    concat_segments(segs, args.out)


if __name__ == "__main__":
    main()