#!/usr/bin/env python3
"""
AI-Creator.py - Local Wan 2.2 5B GGUF Edition (AMD DirectML)
Creates YouTube Shorts from 2 historical photos.
"""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import textwrap
import urllib.request
import urllib.parse
import time

from PIL import Image, ImageDraw, ImageFont
import numpy as np
import imageio
import requests

# --- Edge TTS ---
HAS_EDGE_TTS = False
try:
    import asyncio
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    pass

# --- Constants ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "image_collection.db")
TABLE_NAME = "image_comp"

WIDTH = 1280
HEIGHT = 720
FPS = 24
STATIC_SECONDS = 7
MOTION_SECONDS = 4

COMFY_API_URL = "http://127.0.0.1:8188"
LOCAL_CACHE_DIR = os.path.join(BASE_DIR, "video_cache")
os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)


# --- Utilities ---
def find_ffmpeg():
    import shutil
    for c in ["ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]:
        if shutil.which(c):
            return c
    print("❌ ffmpeg not found")
    return "ffmpeg"


def db_connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def clean_text(t):
    if not t:
        return ""
    t = t.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", t).strip()


# --- Narration ---
def generate_narration(description, index):
    desc = clean_text(description) or "This photo captures a moment most people have never seen."
    if index == 0:
        hook = "At first glance, this looks like just another old photo..."
    else:
        hook = "But this next image hides an even stranger detail..."
    body = f"{desc} Look closely at the faces, the posture, and the tiny details in the background."
    tease = "The story behind this moment is far more intense than it appears."
    return f"{hook} {body} {tease}"


# --- Audio ---
async def _speak(text, out_path):
    communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
    await communicate.save(out_path)


def save_audio(text, out_path):
    if not HAS_EDGE_TTS:
        print("⚠️ Edge TTS not installed. Skipping audio.")
        return False
    try:
        asyncio.run(_speak(text, out_path))
        print(f"🎤 Audio saved: {out_path}")
        return True
    except Exception as e:
        print(f"❌ Audio failed: {e}")
        return False


# --- Static Frame ---
def render_static_frame(image_bytes, caption):
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        img.thumbnail((int(WIDTH * 0.92), int(HEIGHT * 0.78)), Image.Resampling.LANCZOS)

        bg = Image.new("RGB", (WIDTH, HEIGHT), (10, 10, 18))
        x = (WIDTH - img.width) // 2
        y = (HEIGHT - img.height) // 2
        bg.paste(img, (x, y))

        draw = ImageDraw.Draw(bg)
        try:
            font = ImageFont.truetype("arial.ttf", 34)
        except:
            font = ImageFont.load_default()

        lines = textwrap.wrap(clean_text(caption), 52)
        bar_h = len(lines) * 40 + 30
        overlay = Image.new("RGBA", (WIDTH, bar_h), (0, 0, 0, 190))
        d2 = ImageDraw.Draw(overlay)
        yy = 15
        for line in lines:
            d2.text((40, yy), line, font=font, fill=(240, 240, 240))
            yy += 40
        bg.paste(overlay, (0, HEIGHT - bar_h), overlay)

        return np.array(bg)


def write_video(frames, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with imageio.get_writer(path, fps=FPS, codec="libx264", quality=8, macro_block_size=1) as w:
        for f in frames:
            w.append_data(f)


# --- Hash ---
def hash_image(image_bytes):
    return hashlib.sha1(image_bytes).hexdigest()


# --- Local Wan 2.2 GGUF Generation ---
def local_wan_generate(image_bytes, prompt):
    img_hash = hash_image(image_bytes)
    cache_path = os.path.join(LOCAL_CACHE_DIR, f"{img_hash}.mp4")

    if os.path.exists(cache_path):
        print(f"♻️ Using cached video: {cache_path}")
        return cache_path

    print("📤 Uploading image to ComfyUI...")
    try:
        files = {"image": (f"{img_hash}.png", image_bytes, "image/png")}
        up_req = requests.post(f"{COMFY_API_URL}/upload/image", files=files, timeout=30)
        up_req.raise_for_status()
        comfy_filename = up_req.json()["name"]
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return None

    # Improved Workflow for Wan 2.2 5B GGUF (adjust model names as needed)
    workflow = {
        "3": {  # Unet Loader GGUF
            "inputs": {"unet_name": "Wan2.2-TI2V-5B-Q3_K_M.gguf"},
            "class_type": "UnetLoaderGGUF"
        },
        "6": {  # Positive Prompt
            "inputs": {
                "text": f"A vintage historical photograph brought to life with subtle natural movements, gentle breathing, slight head turns, cinematic lighting. {prompt}",
                "clip": ["38", 0]   # Link to CLIP loader (add node if needed)
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {  # Negative Prompt
            "inputs": {
                "text": "text, watermark, low quality, blurry, distorted, fast motion, static, deformed",
                "clip": ["38", 0]
            },
            "class_type": "CLIPTextEncode"
        },
        "10": {  # VAE
            "inputs": {"vae_name": "wan2.2_vae.safetensors"},
            "class_type": "VAELoader"
        },
        "15": {  # CLIP Vision
            "inputs": {"clip_name": "clip_vision_h.safetensors"},
            "class_type": "CLIPVisionLoader"
        },
        "20": {  # Load Image
            "inputs": {"image": comfy_filename},
            "class_type": "LoadImage"
        },
        "55": {  # Image to Video Latent
            "inputs": {
                "vae": ["10", 0],
                "start_image": ["20", 0],
                "width": 640,
                "height": 360,
                "length": MOTION_SECONDS * FPS,
                "batch_size": 1
            },
            "class_type": "Wan22ImageToVideoLatent"   # or WanImageToVideo if using wrapper
        },
        "25": {  # KSampler
            "inputs": {
                "seed": 2026,
                "steps": 20,
                "cfg": 5.5,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["3", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["55", 0]
            },
            "class_type": "KSampler"
        },
        "35": {  # Decode
            "inputs": {
                "samples": ["25", 0],
                "vae": ["10", 0]
            },
            "class_type": "VAEDecode"
        },
        "40": {  # Save Image (will be video frames)
            "inputs": {
                "filename_prefix": f"Wan22_{img_hash}",
                "images": ["35", 0]
            },
            "class_type": "SaveImage"
        }
    }

    print("🎬 Queuing Wan 2.2 generation...")
    try:
        req = urllib.request.Request(
            f"{COMFY_API_URL}/prompt",
            data=json.dumps({"prompt": workflow}).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        response = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))
        prompt_id = response['prompt_id']

        print("⏳ Waiting for generation (this may take several minutes)...")
        for _ in range(120):  # 10+ minutes timeout
            time.sleep(8)
            try:
                hist = json.loads(urllib.request.urlopen(f"{COMFY_API_URL}/history/{prompt_id}").read().decode())
                if prompt_id in hist and hist[prompt_id].get('outputs'):
                    outputs = hist[prompt_id]['outputs']
                    for node_id, data in outputs.items():
                        if 'images' in data:
                            img_info = data['images'][0]
                            video_url = f"{COMFY_API_URL}/view?filename={urllib.parse.quote(img_info['filename'])}&subfolder={urllib.parse.quote(img_info.get('subfolder',''))}&type={img_info.get('type','output')}"
                            out_bytes = requests.get(video_url).content
                            with open(cache_path, "wb") as f:
                                f.write(out_bytes)
                            print(f"✅ Video cached: {cache_path}")
                            return cache_path
            except:
                pass
        print("⚠️ Timeout waiting for ComfyUI output.")
        return None
    except Exception as e:
        print(f"❌ Wan generation failed: {e}")
        return None


# --- Build Segment ---
def build_segment(row, index, outdir, with_audio=True):
    desc = clean_text(row["description"] or row.get("xml_title", ""))
    narration_text = generate_narration(desc, index)

    seg_dir = os.path.join(outdir, f"segment_{index+1}")
    os.makedirs(seg_dir, exist_ok=True)

    audio_path = os.path.join(seg_dir, "audio.mp3")
    has_audio = save_audio(narration_text, audio_path) if with_audio else False

    # Static part
    static_frame = render_static_frame(row["file_data"], narration_text)
    static_frames = [static_frame] * (STATIC_SECONDS * FPS)
    static_video = os.path.join(seg_dir, "static.mp4")
    write_video(static_frames, static_video)

    # Motion part
    local_video = local_wan_generate(row["file_data"], desc)

    ffmpeg = find_ffmpeg()
    out_video = os.path.join(outdir, f"segment_{index+1}.mp4")

    if local_video:
        print("⚙️ Combining static + motion with FFmpeg...")
        filter_str = (
            f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[s0];"
            f"[1:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[s1];"
            f"[s0][s1]concat=n=2:v=1:a=0[v]"
        )
        cmd = [ffmpeg, "-y", "-i", static_video, "-i", local_video]
        if has_audio:
            cmd += ["-i", audio_path]
            filter_str += ";[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a]"
        cmd += ["-filter_complex", filter_str, "-map", "[v]"]
        if has_audio:
            cmd += ["-map", "[a]", "-c:a", "aac", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", out_video]
    else:
        # Fallback to static only
        filter_str = f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[v]"
        cmd = [ffmpeg, "-y", "-i", static_video]
        if has_audio:
            cmd += ["-i", audio_path]
            filter_str += ";[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a]"
        cmd += ["-filter_complex", filter_str, "-map", "[v]"]
        if has_audio:
            cmd += ["-map", "[a]", "-c:a", "aac", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", out_video]

    subprocess.run(cmd, check=True, capture_output=True)
    print(f"🎬 Segment ready: {out_video}")
    return out_video


# --- Concat ---
def concat_segments(segments, out_path):
    ffmpeg = find_ffmpeg()
    concat_file = os.path.join(BASE_DIR, "segments", "concat.txt")
    os.makedirs(os.path.dirname(concat_file), exist_ok=True)

    with open(concat_file, "w") as f:
        for s in segments:
            f.write(f"file '{os.path.abspath(s)}'\n")

    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", out_path]
    subprocess.run(cmd, check=True)
    print(f"🏁 Final video: {out_path}")


# --- Main ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--out", default=os.path.join(BASE_DIR, "output_video.mp4"))
    parser.add_argument("--no-audio", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"❌ Database not found: {args.db}")
        sys.exit(1)

    conn = db_connect(args.db)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY RANDOM() LIMIT 2")
    rows = cur.fetchall()

    if len(rows) < 2:
        print("❌ Need at least 2 images in the database.")
        sys.exit(1)

    outdir = os.path.join(BASE_DIR, "segments")
    os.makedirs(outdir, exist_ok=True)

    segs = []
    for i, row in enumerate(rows):
        segs.append(build_segment(dict(row), i, outdir, with_audio=not args.no_audio))

    concat_segments(segs, args.out)


if __name__ == "__main__":
    main()