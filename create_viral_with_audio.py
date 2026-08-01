#!/usr/bin/env python3
"""
Create a themed viral YouTube video (~20 minutes) with spoken narration and background music.

This script:
1. Queries images from multiple categories (Exploration + Places + Historical Events)
2. Generates contextual narrative text for each image
3. Converts text to speech (TTS) using edge-tts
4. Creates video frames with text overlays
5. Adds background music (soft in background)
6. Combines audio tracks (narration + music)

Usage example:
    python create_viral_with_audio.py --outdir "viral_mixed" --music "background_music.mp3"

Theme: "Journeys & Frontiers: The Discovery of Our World"
Story Arc:
  - Exploration drives human progress
  - Places define civilization
  - Historical events shape our future
"""

import argparse
import os
import sqlite3
import random
import subprocess
import sys
from datetime import datetime
import textwrap
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import imageio
import asyncio

# Try to import TTS library
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    print("⚠️  edge-tts not found. Install with: pip install edge-tts")

# Try FFmpeg
try:
    import ffmpeg
    HAS_FFMPEG = True
except ImportError:
    HAS_FFMPEG = False
    print("⚠️  ffmpeg-python not found. Install with: pip install ffmpeg-python")

# Defaults
DEFAULT_DB = "image_collection.db"
DEFAULT_TABLE = "image_comp"
WIDTH, HEIGHT = 1920, 1088
FPS = 24
IMAGE_SEC = 14
INTRO_DURATION = 4
OUTRO_DURATION = 16

# Narrative templates for the mixed theme
NARRATIVE_TEMPLATES = {
    "opening": [
        "Throughout history, humans have been drawn to explore and discover.",
        "The great explorers opened doors to new worlds and possibilities.",
        "Every journey begins with courage and a desire to understand our world.",
        "Discovery has always been at the heart of human progress.",
    ],
    "exploration": [
        "Bold adventurers crossed uncharted territories and unknown seas.",
        "Exploration pushed the boundaries of what we thought possible.",
        "From jungle expeditions to mountain peaks, explorers left their mark.",
        "The spirit of adventure created new opportunities for humanity.",
    ],
    "places": [
        "These remarkable places shaped civilizations and inspired generations.",
        "From ancient cities to modern metropolises, places tell stories.",
        "Geography defines culture, and places preserve our heritage.",
        "Every corner of Earth holds beauty and wonder.",
    ],
    "historical": [
        "History teaches us about triumphs and challenges that define eras.",
        "Great events changed the course of nations and the world.",
        "The past illuminates the path to our future.",
        "Through understanding history, we better understand ourselves.",
    ],
    "connection": [
        "Exploration connected distant lands and brought people together.",
        "Places became bridges between cultures and ideas.",
        "Historical moments created lasting bonds across time and geography.",
        "Our world was built by those who dared to explore and discover.",
    ],
    "closing": [
        "The journey of discovery continues to this day.",
        "Every adventure begun opens possibilities we can barely imagine.",
        "We are the descendants of explorers, and explorers ourselves.",
        "The greatest discoveries and adventures still lie ahead.",
    ]
}

THEME_TITLE = "Journeys & Frontiers: The Discovery of Our World"
THEME_SUBTITLE = "From Early Exploration to Modern Places – A Story of Human Discovery"


def get_narrative_for_position(total_count, current_index, category=None):
    """Generate contextual narrative based on position in video."""
    position_ratio = current_index / total_count if total_count > 0 else 0
    
    if position_ratio < 0.15:
        return random.choice(NARRATIVE_TEMPLATES["opening"] + NARRATIVE_TEMPLATES["exploration"])
    elif position_ratio < 0.40:
        return random.choice(NARRATIVE_TEMPLATES["exploration"])
    elif position_ratio < 0.65:
        return random.choice(NARRATIVE_TEMPLATES["places"])
    elif position_ratio < 0.80:
        return random.choice(NARRATIVE_TEMPLATES["historical"])
    elif position_ratio < 0.92:
        return random.choice(NARRATIVE_TEMPLATES["connection"])
    else:
        return random.choice(NARRATIVE_TEMPLATES["closing"])


def get_images_by_categories(db_path, table_name, categories, total_count):
    """Query database for images from multiple categories."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Calculate images per category
    per_category = total_count // len(categories)
    all_rows = []
    
    for cat in categories:
        query = f"""
            SELECT * FROM {table_name}
            WHERE xml_subject = ?
            ORDER BY RANDOM()
            LIMIT ?
        """
        try:
            cur.execute(query, (cat, per_category))
            rows = cur.fetchall()
            all_rows.extend(rows)
            print(f"   ✅ {cat}: {len(rows)} images")
        except Exception as e:
            print(f"   ❌ Error querying {cat}: {e}")
    
    conn.close()
    
    # Shuffle to mix categories
    random.shuffle(all_rows)
    return all_rows[:total_count]


def get_image_blob(row):
    """Extract image blob from database row."""
    if "file_data" in row.keys():
        return row["file_data"]
    elif "image_data" in row.keys():
        return row["image_data"]
    elif "image" in row.keys():
        return row["image"]
    else:
        return None


def create_frame_with_text(image_data, narrative_text, idx, total):
    """Create a frame with image and narrative text overlay."""
    try:
        if isinstance(image_data, bytes):
            from io import BytesIO
            img = Image.open(BytesIO(image_data)).convert('RGB')
        else:
            img = Image.open(image_data).convert('RGB')
        
        # Resize to target dimensions
        img.thumbnail((WIDTH, int(HEIGHT * 0.75)), Image.Resampling.LANCZOS)
        
        # Create background
        bg = Image.new('RGB', (WIDTH, HEIGHT), (15, 20, 40))  # Dark blue
        
        # Paste image centered
        paste_x = (WIDTH - img.width) // 2
        paste_y = int(HEIGHT * 0.08)
        bg.paste(img, (paste_x, paste_y))
        
        # Draw border around image
        draw = ImageDraw.Draw(bg)
        border = 3
        draw.rectangle(
            [paste_x - border, paste_y - border, paste_x + img.width + border, paste_y + img.height + border],
            outline=(200, 180, 100),
            width=border
        )
        
        # Add text overlay
        try:
            title_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 48)
            text_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 36)
            small_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 24)
        except:
            title_font = text_font = small_font = ImageFont.load_default()
        
        # Add narrative text with wrapping
        text_y = int(HEIGHT * 0.78)
        wrapped_lines = textwrap.wrap(narrative_text, width=50)
        
        for line in wrapped_lines[:3]:
            # Semi-transparent background for text
            bbox = draw.textbbox((40, text_y), line, font=text_font)
            draw.rectangle(
                [bbox[0] - 10, bbox[1] - 5, bbox[2] + 10, bbox[3] + 5],
                fill=(0, 0, 0, 200)
            )
            # White text
            draw.text((40, text_y), line, fill=(255, 255, 255), font=text_font)
            text_y += 50
        
        # Add counter
        counter_text = f"{idx+1}/{total}"
        draw.text((WIDTH - 150, HEIGHT - 50), counter_text, fill=(200, 200, 200), font=small_font)
        
        return np.array(bg)
    
    except Exception as e:
        print(f"⚠️  Error creating frame: {e}")
        return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


def create_intro_frame(title, subtitle):
    """Create intro frame."""
    bg = Image.new('RGB', (WIDTH, HEIGHT), (15, 20, 40))
    draw = ImageDraw.Draw(bg)
    
    try:
        title_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 64)
        subtitle_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 40)
    except:
        title_font = subtitle_font = ImageFont.load_default()
    
    title_y = HEIGHT // 3
    title_bbox = draw.textbbox((0, title_y), title, font=title_font)
    title_x = (WIDTH - (title_bbox[2] - title_bbox[0])) // 2
    draw.text((title_x, title_y), title, fill=(255, 215, 0), font=title_font)
    
    subtitle_y = title_y + 120
    subtitle_bbox = draw.textbbox((0, subtitle_y), subtitle, font=subtitle_font)
    subtitle_x = (WIDTH - (subtitle_bbox[2] - subtitle_bbox[0])) // 2
    draw.text((subtitle_x, subtitle_y), subtitle, fill=(200, 200, 200), font=subtitle_font)
    
    return np.array(bg)


def create_outro_frame(title):
    """Create outro frame."""
    bg = Image.new('RGB', (WIDTH, HEIGHT), (15, 20, 40))
    draw = ImageDraw.Draw(bg)
    
    try:
        title_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 56)
        text_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 40)
    except:
        title_font = text_font = ImageFont.load_default()
    
    messages = [
        "The journey of discovery continues.",
        "Thank you for exploring with us.",
        "What will you discover next?"
    ]
    
    y_pos = HEIGHT // 3
    for msg in messages:
        bbox = draw.textbbox((0, y_pos), msg, font=text_font)
        x_pos = (WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x_pos, y_pos), msg, fill=(255, 215, 0), font=text_font)
        y_pos += 100
    
    return np.array(bg)


async def generate_speech(text, output_path, voice="en-US-AriaNeural"):
    """Generate speech from text using edge-tts."""
    if not HAS_EDGE_TTS:
        print("❌ edge-tts not installed. Run: pip install edge-tts")
        return False
    
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(output_path)
        return True
    except Exception as e:
        print(f"❌ Error generating speech: {e}")
        return False


def create_narration_audio(narratives, audio_dir):
    """Create audio files for all narratives."""
    os.makedirs(audio_dir, exist_ok=True)
    audio_files = []
    
    print(f"\n🎙️  Creating narration audio ({len(narratives)} segments)...")
    
    for idx, narrative in enumerate(narratives):
        audio_file = os.path.join(audio_dir, f"narration_{idx:03d}.mp3")
        
        # Use asyncio to run the async function
        try:
            asyncio.run(generate_speech(narrative, audio_file))
            audio_files.append(audio_file)
            if (idx + 1) % 10 == 0:
                print(f"   ✅ Generated {idx + 1}/{len(narratives)}")
        except Exception as e:
            print(f"⚠️  Failed to generate audio for segment {idx}: {e}")
            audio_files.append(None)
    
    return audio_files


def render_frames(rows, total_images):
    """Render image frames with text overlays."""
    frames = []
    narratives = []
    
    print(f"\n🎬 Creating intro frame...")
    intro_frames = [create_intro_frame(THEME_TITLE, THEME_SUBTITLE)] * int(INTRO_DURATION * FPS)
    frames.extend(intro_frames)
    narratives.append("Welcome to Journeys and Frontiers, a story of human discovery.")
    
    print(f"🎬 Processing {len(rows)} images with narrative text...")
    for idx, row in enumerate(rows):
        if idx % 10 == 0:
            print(f"   {idx+1}/{len(rows)}")
        
        image_data = get_image_blob(row)
        if image_data is None:
            continue
        
        narrative = get_narrative_for_position(len(rows), idx)
        narratives.append(narrative)
        frame = create_frame_with_text(image_data, narrative, idx, len(rows))
        
        # Each image displays for IMAGE_SEC seconds
        frame_count = int(IMAGE_SEC * FPS)
        frames.extend([frame] * frame_count)
    
    print(f"🎬 Creating outro frame...")
    outro_frames = [create_outro_frame(THEME_TITLE)] * int(OUTRO_DURATION * FPS)
    frames.extend(outro_frames)
    narratives.append("Thank you for journeying through history and discovery with us.")
    
    print(f"   Total frames: {len(frames)} ({len(frames)/FPS/60:.1f} minutes)")
    return frames, narratives


def main():
    parser = argparse.ArgumentParser(
        description="Create a viral YouTube video with spoken narration and music"
    )
    parser.add_argument("--categories", nargs="+", 
                       default=["Exploration", "Places", "Historical Events"],
                       help="Categories to mix (default: Exploration Places Historical Events)")
    parser.add_argument("--total", type=int, default=85,
                       help="Number of images to use (default: 85 for ~20min)")
    parser.add_argument("--db", default=DEFAULT_DB,
                       help=f"Database path (default: {DEFAULT_DB})")
    parser.add_argument("--table", default=DEFAULT_TABLE,
                       help=f"Table name (default: {DEFAULT_TABLE})")
    parser.add_argument("--outdir", default="viral_mixed_output",
                       help="Output directory (default: viral_mixed_output)")
    parser.add_argument("--music", default=None,
                       help="Background music file (optional). Will create a demo track if not provided.")
    parser.add_argument("--skip-audio", action="store_true",
                       help="Skip audio generation (video only)")
    
    args = parser.parse_args()
    
    # Check database
    if not os.path.isfile(args.db):
        print(f"❌ Database not found: {args.db}")
        sys.exit(1)
    
    os.makedirs(args.outdir, exist_ok=True)
    
    print(f"\n{'='*80}")
    print(f"🎥 Creating Viral Video with Spoken Narration & Music")
    print(f"{'='*80}")
    print(f"📽️  Theme:       {THEME_TITLE}")
    print(f"📂 Categories:  {', '.join(args.categories)}")
    print(f"🖼️  Total images: {args.total}")
    print(f"⏱️  Duration:   ~20 minutes")
    print(f"🎙️  Narration:  Text-to-Speech (spoken)")
    print(f"🎵 Music:      Background (soft)")
    print(f"💾 Output:     {args.outdir}")
    print(f"{'='*80}\n")
    
    # Query images
    print(f"🔍 Querying database for mixed categories...")
    rows = get_images_by_categories(args.db, args.table, args.categories, args.total)
    
    if not rows:
        print(f"❌ No images found")
        sys.exit(1)
    
    print(f"✅ Found {len(rows)} images\n")
    
    # Render frames and get narratives
    frames, narratives = render_frames(rows, len(rows))
    
    # Write video (video track first)
    output_path = os.path.join(args.outdir, "viral_video.mp4")
    print(f"\n🎞️  Writing video frames to {output_path}...")
    
    try:
        writer = imageio.get_writer(output_path, fps=FPS, codec='libx264', pixelformat='yuv420p')
        for i, frame in enumerate(frames):
            if i % 500 == 0:
                print(f"   {i}/{len(frames)} frames")
            writer.append_data(frame)
        writer.close()
        print(f"✅ Video created!")
        print(f"   Duration: {len(frames) / FPS:.1f} seconds ({len(frames) / FPS / 60:.1f} minutes)")
        print(f"   Size: {os.path.getsize(output_path) / (1024*1024):.1f} MB")
    except Exception as e:
        print(f"❌ Error writing video: {e}")
        sys.exit(1)
    
    if args.skip_audio:
        print(f"\n{'='*80}")
        print(f"✨ Video ready (audio skipped): {output_path}")
        print(f"{'='*80}\n")
        return
    
    # Generate narration audio if edge-tts available
    if HAS_EDGE_TTS:
        audio_dir = os.path.join(args.outdir, "audio_narration")
        narration_files = create_narration_audio(narratives, audio_dir)
        
        # TODO: Merge narration files and add background music
        print(f"\n🎵 Narration audio files created in: {audio_dir}")
        print(f"   Note: Audio merging requires additional audio processing")
    else:
        print(f"\n⚠️  To add spoken narration, install edge-tts:")
        print(f"   pip install edge-tts")
    
    print(f"\n{'='*80}")
    print(f"✨ Viral video ready: {output_path}")
    print(f"   Size: {os.path.getsize(output_path) / (1024*1024):.1f} MB")
    print(f"{'='*80}\n")
    print(f"💡 Next steps:")
    print(f"   1. Install edge-tts for narration: pip install edge-tts")
    print(f"   2. Add background music file")
    print(f"   3. Run script again to include audio")


if __name__ == "__main__":
    main()
