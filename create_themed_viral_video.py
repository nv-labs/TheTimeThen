#!/usr/bin/env python3
"""
Create a themed viral YouTube video (~20 minutes) with a narrative story overlay.

This script:
1. Queries images from a specific category (e.g., 'Exploration')
2. Generates contextual narrative text for each image
3. Creates a video where each image displays for 14 seconds with text overlay
4. Total duration: ~20 minutes with compelling story arc

Usage example:
    python create_themed_viral_video.py --category "Exploration" --total 85 --outdir "viral_video_exploration"

Theme: "A Century of Human Discovery: The Unstoppable Spirit of Exploration"
Story Arc:
  - How humans conquered new frontiers
  - Evolution from dangerous expeditions to modern exploration
  - The spirit of discovery that defines humanity
"""

import argparse
import asyncio
import os
import re
import sqlite3
import random
import requests
import urllib.parse
from datetime import datetime
import textwrap
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import numpy as np
import imageio
from openai import OpenAI

# Try to import edge-tts for better narration
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    print("⚠️  edge-tts not found. Install with: pip install edge-tts")

# Defaults
DEFAULT_DB = "image_collection.db"
DEFAULT_TABLE = "image_comp"
WIDTH, HEIGHT = 1920, 1088
FPS = 24
IMAGE_SEC = 14
INTRO_DURATION = 3.5
OUTRO_DURATION = 16
DEFAULT_VOICE = "en-US-AriaNeural"
VOICE_FALLBACKS = [
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-US-AmberNeural",
    "en-GB-LibbyNeural"
]

# Narrative templates for different sections of the exploration story
EXPLORATION_NARRATIVE_TEMPLATES = {
    "opening": [
        "Since the dawn of time, humans have yearned to explore the unknown.",
        "The greatest achievements come from those brave enough to venture beyond.",
        "Every explorer starts with a dream and a determination to discover.",
        "History is written by those who dared to explore.",
    ],
    "early_exploration": [
        "The early pioneers faced impossible odds with nothing but courage.",
        "Ancient explorers crossed vast oceans with primitive tools.",
        "These brave souls mapped uncharted territories.",
        "Exploration began with a single step into the unknown.",
    ],
    "aviation": [
        "The Wright Brothers changed everything when they conquered the sky.",
        "Flight opened new frontiers and connected distant worlds.",
        "From first flight to transcontinental journeys in decades.",
        "The skies became the new frontier for human exploration.",
    ],
    "mountain_exploration": [
        "These peaks challenged the greatest mountaineers throughout history.",
        "Everest, K2, and countless summits tested human limits.",
        "Each success inspired the next generation of climbers.",
        "Mountains have always called to the adventurous spirit.",
    ],
    "space_age": [
        "Then humanity reached for the stars themselves.",
        "The space age revealed our true potential.",
        "From satellites to moon landings, we touched the cosmos.",
        "Exploration entered a new dimension entirely.",
    ],
    "modern_exploration": [
        "Today's explorers work in laboratories and deep oceans.",
        "We explore the smallest particles and deepest trenches.",
        "Modern discovery builds on centuries of adventurous spirit.",
        "The frontier is always ahead of us, waiting to be discovered.",
    ],
    "closing": [
        "The human spirit of exploration will never fade.",
        "Every achievement today becomes the stepping stone for tomorrow.",
        "We are the descendants of explorers, and explorers ourselves.",
        "The greatest discoveries are yet to come.",
    ]
}

THEME_TITLE = "A Century of Human Discovery: The Unstoppable Spirit of Exploration"
THEME_SUBTITLE = "From Early Pioneers to Modern Frontiers – The Story of Human Curiosity"


def clean_metadata_text(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace('_', ' ').replace('--', ' ').replace('-', ' ')
    text = re.sub(r"\.(jpg|jpeg|png|gif)$", '', text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", ' ', text).strip()
    return text


def extract_year(text):
    if not text:
        return None
    match = re.search(r"\b(18|19|20)\d{2}\b", text)
    return match.group(0) if match else None


def build_specific_narrative(row, category=None):
    description = clean_metadata_text(row['description']) if 'description' in row.keys() and row['description'] else None
    title = clean_metadata_text(row['xml_title']) if 'xml_title' in row.keys() and row['xml_title'] else None
    subject = clean_metadata_text(row['xml_subject']) if 'xml_subject' in row.keys() and row['xml_subject'] else None
    filename = clean_metadata_text(row['filename']) if 'filename' in row.keys() and row['filename'] else None
    source = clean_metadata_text(row['source_url']) if 'source_url' in row.keys() and row['source_url'] else None

    meta_parts = []
    if description:
        meta_parts.append(description)
    if title and title not in meta_parts:
        meta_parts.append(title)
    if subject and subject not in meta_parts:
        meta_parts.append(subject)
    if filename and filename not in meta_parts:
        meta_parts.append(filename)
    if source and source not in meta_parts:
        meta_parts.append(source)

    main_text = meta_parts[0] if meta_parts else None
    year = extract_year(main_text or '')
    age_phrase = f" in {year}" if year else ''

    category_phrase = ''
    if category:
        cat_name = clean_metadata_text(category)
        if cat_name and main_text and cat_name.lower() not in main_text.lower():
            category_phrase = f" From the {cat_name} archive, this image tells its own story."
        elif cat_name:
            category_phrase = f" It is part of the {cat_name} collection."

    # Fetch internet context using all possible metadata fields
    internet_context = fetch_internet_context([title, description, subject, filename])

    # Narrative templates for variety, all with unique phrasing
    templates = []
    if description:
        templates.append(f"{description}. {internet_context}" if internet_context else f"{description}.")
        templates.append(f"Here's a glimpse: {description}. {internet_context}" if internet_context else f"Here's a glimpse: {description}.")
    if title and subject:
        templates.append(f"Titled '{title}', this image features {subject.lower()}. {internet_context}" if internet_context else f"Titled '{title}', this image features {subject.lower()}.")
        templates.append(f"'{title}' is the name, and {subject.lower()} is the focus. {internet_context}" if internet_context else f"'{title}' is the name, and {subject.lower()} is the focus.")
    if title:
        templates.append(f"Known as '{title}'{age_phrase}. {internet_context}" if internet_context else f"Known as '{title}'{age_phrase}.")
        templates.append(f"This moment is called '{title}'. {internet_context}" if internet_context else f"This moment is called '{title}'.")
    if subject:
        templates.append(f"A part of the {subject} collection{age_phrase}. {internet_context}" if internet_context else f"A part of the {subject} collection{age_phrase}.")
        templates.append(f"The subject here: {subject}. {internet_context}" if internet_context else f"The subject here: {subject}.")
    if source:
        templates.append(f"From the archive: {source}. {internet_context}" if internet_context else f"From the archive: {source}.")
    if main_text:
        templates.append(f"Scene: {main_text}. {internet_context}" if internet_context else f"Scene: {main_text}.")
    # Remove duplicates and empty
    templates = list({t.strip() for t in templates if t and t.strip()})
    random.shuffle(templates)
    if templates:
        return templates[0]
    # Fallback: always generate a new phrase
    fallback = generate_narrative_for_image(get_image_context(row), None, category)
    # Add a random prefix to avoid repetition
    fallback_prefixes = [
        "A unique moment:",
        "Captured in history:",
        "A story unfolds:",
        "A rare glimpse:",
        "A special scene:",
        "A different perspective:"
    ]
    return f"{random.choice(fallback_prefixes)} {fallback}"


# --- New function to fetch internet context ---
def fetch_internet_context(query):
    """
    Fetch a short summary from Wikipedia for the given queries (title/subject/description/filename).
    Tries each query and falls back to Wikipedia search if needed.
    Returns a 1-2 sentence summary or empty string if not found.
    """
    tried = set()
    # Support both old and new call signatures
    if isinstance(query, (list, tuple)):
        queries = query
    else:
        queries = [query]
    for q in queries:
        if not q or q in tried:
            continue
        tried.add(q)
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(q)}"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                extract = data.get("extract")
                if extract:
                    sentences = extract.split('. ')
                    return '. '.join(sentences[:2]).strip()
            # If not found, try Wikipedia search API
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(q)}&format=json"
            search_resp = requests.get(search_url, timeout=2)
            if search_resp.status_code == 200:
                search_data = search_resp.json()
                search_results = search_data.get('query', {}).get('search', [])
                if search_results:
                    # Try the first search result
                    page_title = search_results[0]['title']
                    url2 = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page_title)}"
                    resp2 = requests.get(url2, timeout=2)
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        extract2 = data2.get("extract")
                        if extract2:
                            sentences2 = extract2.split('. ')
                            return '. '.join(sentences2[:2]).strip()
        except Exception:
            continue
    return ""


def get_image_context(row):
    """
    Extract the richest context text available from the database row.
    """
    context_fields = [
        "description",
        "xml_title",
        "xml_subject",
        "filename",
        "source_url",
        "subject",
        "AI_category",
        "text",
        "caption",
        "tags",
        "category"
    ]

    for field in context_fields:
        if field in row.keys() and row[field]:
            value = clean_metadata_text(row[field])
            if value:
                return value
    return None


def generate_narrative_for_image(image_context, position_ratio, category=None):
    """
    Generate specific narrative text for an image based on its context.

    If image context is available (subject, description), creates targeted
    narrative about that specific person, place, or event.
    If not available, falls back to generic exploration narrative.
    """

    if image_context and len(image_context) > 0:
        context_lower = image_context.lower()
        year_match = re.search(r"\b(18|19|20)\d{2}\b", image_context)
        year_phrase = f" from {year_match.group(0)}" if year_match else ""

        if any(name in context_lower for name in ["elvis", "marilyn", "sinatra", "audrey", "michael jackson", "madonna", "beyonce", "frank sinatra"]):
            templates = [
                f"This photo of {image_context} feels like a time capsule from the music and film world.",
                f"{image_context} defined an era, and this image takes us right into that moment{year_phrase}.",
                f"The charisma of {image_context} is unmistakable in this frame.",
                f"This is a classic snapshot of {image_context}, a true icon of entertainment.",
            ]
        elif any(name in context_lower for name in ["hitler", "churchill", "kennedy", "lincoln", "roosevelt", "reagan", "stalin", "de gaulle"]):
            templates = [
                f"This image captures a powerful moment in political history{year_phrase}.",
                f"{image_context} reminds us of the leaders and events that shaped the 20th century.",
                f"This photograph shows a historic figure at a defining moment.",
                f"The subject here tells a story of power, politics, and a world in motion.",
            ]
        elif any(word in context_lower for word in ["concert", "performance", "show", "stage", "audience", "singing"]):
            templates = [
                f"This scene captures the energy and drama of a live performance.",
                f"{image_context} shows a moment when the crowd was completely caught up in the show.",
                f"The stage presence here tells the story of an unforgettable event.",
                f"A moment like this is what made this era so electric.",
            ]
        elif any(word in context_lower for word in ["portrait", "posing", "profile", "tense", "smiling", "looking"]):
            templates = [
                f"This portrait shows the character and emotion behind the face.",
                f"{image_context} captures a more intimate, human side of history.",
                f"Here we feel the personality shining through the image.",
                f"This moment is as much about mood as it is about the subject.",
            ]
        elif any(word in context_lower for word in ["politician", "politicians", "president", "minister", "leader", "parliament"]):
            templates = [
                f"This photo belongs to the world of politics and public life.",
                f"{image_context} shows how leaders were presented to the public.",
                f"This scene documents a political moment from the past.",
                f"A single image can say a lot about the politics of its time.",
            ]
        elif any(word in context_lower for word in ["city", "new york", "london", "paris", "hollywood", "studio", "street"]):
            templates = [
                f"This image transports us to a specific place and era.",
                f"The location and atmosphere in this photo tell a story of a bygone time.",
                f"This scene is full of the textures and details of its city.",
                f"We can almost hear the streets and feel the energy of this place.",
            ]
        else:
            templates = [
                f"This photo captures a remarkable moment in history{year_phrase}.",
                f"{image_context} gives us a window into the people and stories of the past.",
                f"This moment feels true to the era it represents.",
                f"The details in this image help us understand the story behind it.",
            ]

        if category:
            cat_name = clean_metadata_text(category)
            if cat_name and cat_name.lower() not in context_lower:
                templates.append(f"This {cat_name.lower()} image is part of a larger story from the archive.")

        return random.choice(templates)

    position_ratio = position_ratio if position_ratio is not None else 0.5

    if position_ratio < 0.15:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["opening"] + 
                           EXPLORATION_NARRATIVE_TEMPLATES["early_exploration"])
    elif position_ratio < 0.30:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["early_exploration"])
    elif position_ratio < 0.50:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["aviation"])
    elif position_ratio < 0.70:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["mountain_exploration"])
    elif position_ratio < 0.85:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["space_age"])
    elif position_ratio < 0.95:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["modern_exploration"])
    else:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["closing"])
    
    # Fallback: use position-based generic narrative
    position_ratio = position_ratio if position_ratio is not None else 0.5
    
    if position_ratio < 0.15:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["opening"] + 
                           EXPLORATION_NARRATIVE_TEMPLATES["early_exploration"])
    elif position_ratio < 0.30:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["early_exploration"])
    elif position_ratio < 0.50:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["aviation"])
    elif position_ratio < 0.70:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["mountain_exploration"])
    elif position_ratio < 0.85:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["space_age"])
    elif position_ratio < 0.95:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["modern_exploration"])
    else:
        return random.choice(EXPLORATION_NARRATIVE_TEMPLATES["closing"])


def get_images_by_category(db_path, table_name, category, total_count):
    """
    Query database for images with specific category.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Check if category column exists
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = {r[1] for r in cur.fetchall()}
    
    # Try different column names
    category_col = None
    for candidate in ["AI_category", "category", "xml_subject", "xml_collection", "subject"]:
        if candidate in cols:
            category_col = candidate
            break

    if category_col is None:
        print(f"❌ No category column found in {table_name}")
        available = ", ".join(cols)
        print(f"   Available columns: {available}")
        return []
    
    # Query images with specific category
    query = f"""
        SELECT * FROM {table_name}
        WHERE {category_col} = ?
        ORDER BY RANDOM()
        LIMIT ?
    """
    
    try:
        cur.execute(query, (category, total_count))
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ Error querying database: {e}")
        conn.close()
        return []


def get_available_categories(db_path, table_name):
    """List all available categories in database."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Try different column names
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = {r[1] for r in cur.fetchall()}
    
    category_col = None
    for candidate in ["AI_category", "category", "xml_subject", "xml_collection", "subject"]:
        if candidate in cols:
            category_col = candidate
            break

    if category_col is None:
        conn.close()
        return []
    
    try:
        query = f"SELECT DISTINCT {category_col} FROM {table_name} ORDER BY {category_col}"
        cur.execute(query)
        categories = [r[0] for r in cur.fetchall() if r[0]]
        conn.close()
        return categories
    except Exception as e:
        print(f"❌ Error querying categories: {e}")
        conn.close()
        return []


def get_image_blob(row):
    """Extract image blob from database row."""
    if "image_data" in row.keys():
        return row["image_data"]
    elif "file_data" in row.keys():
        return row["file_data"]
    elif "image" in row.keys():
        return row["image"]
    else:
        return None


def create_frame_with_text(image_data, narrative_text, idx, total):
    """
    Create a frame with full image displayed (no cropping) and narrative text overlay.
    Uses letterboxing to fit image while preserving aspect ratio and full visibility.
    """
    try:
        if isinstance(image_data, bytes):
            from io import BytesIO
            img = Image.open(BytesIO(image_data)).convert('RGB')
        else:
            img = Image.open(image_data).convert('RGB')
        
        # Create background with blurred version of image
        bg_image = img.copy()
        bg_image = ImageOps.fit(bg_image, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        bg_image = bg_image.filter(ImageFilter.GaussianBlur(radius=20))
        bg_overlay = Image.new('RGB', (WIDTH, HEIGHT), (8, 12, 24))
        bg = Image.blend(bg_image, bg_overlay, alpha=0.35)
        
        # Resize the main image to fit within frame while preserving aspect ratio (NO CROPPING)
        # Leave room for text at bottom (76% of height)
        max_width = int(WIDTH * 0.90)
        max_height = int(HEIGHT * 0.70)
        
        # Calculate scaling to fit image within bounds while preserving aspect ratio
        img_width, img_height = img.size
        scale_w = max_width / img_width if img_width > 0 else 0
        scale_h = max_height / img_height if img_height > 0 else 0
        scale = min(scale_w, scale_h, 1.0)  # Don't upscale
        
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Center the image horizontally and place it in upper portion
        paste_x = (WIDTH - new_width) // 2
        paste_y = int(HEIGHT * 0.05)
        
        # Add a subtle border for depth
        draw = ImageDraw.Draw(bg)
        border_padding = 8
        draw.rectangle(
            [paste_x - border_padding, paste_y - border_padding,
             paste_x + new_width + border_padding, paste_y + new_height + border_padding],
            outline=(220, 220, 220),
            width=2
        )
        bg.paste(img_resized, (paste_x, paste_y))
        
        # Add text overlay at bottom
        try:
            text_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 38)
            small_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 26)
        except:
            text_font = small_font = ImageFont.load_default()
        
        caption_bg_top = int(HEIGHT * 0.75)
        caption_bg_height = int(HEIGHT * 0.2)
        draw.rectangle(
            [40, caption_bg_top, WIDTH - 40, caption_bg_top + caption_bg_height],
            fill=(0, 0, 0, 180)
        )
        
        text_y = caption_bg_top + 24
        wrapped_lines = textwrap.wrap(narrative_text, width=56)
        for line in wrapped_lines[:4]:
            bbox = draw.textbbox((60, text_y), line, font=text_font)
            draw.text((60, text_y), line, fill=(245, 245, 245), font=text_font)
            text_y += 46
        
        counter_text = f"{idx+1}/{total}"
        draw.text((WIDTH - 180, HEIGHT - 50), counter_text, fill=(200, 200, 200), font=small_font)
        
        return np.array(bg)
    
    except Exception as e:
        print(f"⚠️  Error creating frame: {e}")
        return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


def generate_intro_text():
    return (
        "Welcome to a celebration of human discovery, "
        "where every image tells the story of exploration."
    )


def generate_outro_text():
    return (
        "The spirit of exploration lives on in every one of us. "
        "Thank you for watching."
    )


async def generate_speech(text, output_path, voice=DEFAULT_VOICE):
    """Generate speech from text using edge-tts."""
    if not HAS_EDGE_TTS:
        print("❌ edge-tts not installed. Run: pip install edge-tts")
        return False

    try:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(output_path)
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 2048:
            return True
        print(f"❌ No audio was written for voice {voice}.")
        return False
    except Exception as e:
        print(f"❌ Error generating speech ({voice}): {e}")
        return False


def get_audio_duration(audio_path):
    """Get audio duration from ffprobe, with fallback."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, check=True
        )
        return float(result.stdout.strip())
    except Exception:
        return IMAGE_SEC


def create_narration_audio(narratives, audio_dir, voice=DEFAULT_VOICE):
    """Create audio files for all narratives and return file paths and durations."""
    os.makedirs(audio_dir, exist_ok=True)
    audio_files = []
    durations = []

    print(f"\n🎙️  Creating narration audio ({len(narratives)} segments)...")
    print(f"    Voice: {voice}")
    print(f"    Output directory: {audio_dir}")

    successful_count = 0
    failed_count = 0

    for idx, narrative in enumerate(narratives):
        audio_file = os.path.join(audio_dir, f"narration_{idx:03d}.mp3")
        success = False
        tried_voices = [voice] + [v for v in VOICE_FALLBACKS if v != voice]

        for attempt_voice in tried_voices:
            try:
                print(f"   [{idx+1}/{len(narratives)}] Generating with {attempt_voice}... ", end="", flush=True)
                success = asyncio.run(generate_speech(narrative, audio_file, voice=attempt_voice))
                
                if success:
                    print("✅")
                    successful_count += 1
                    
                    if attempt_voice != voice:
                        print(f"          (fallback to {attempt_voice})")
                    break
                else:
                    print("❌")
            except Exception as e:
                print(f"❌ Exception: {str(e)[:50]}")
                success = False

        if success and os.path.isfile(audio_file) and os.path.getsize(audio_file) > 2048:
            duration = get_audio_duration(audio_file)
            audio_files.append(audio_file)
            durations.append(duration)
        else:
            print(f"   ⚠️  All voice attempts failed for segment {idx}. Using silence duration.")
            audio_files.append(None)
            durations.append(IMAGE_SEC)
            failed_count += 1

    print(f"\n   Summary: {successful_count} successful, {failed_count} failed")
    return audio_files, durations


def combine_audio_files(audio_files, output_path):
    """Combine multiple mp3 narration segments into one track."""
    valid_files = [f for f in audio_files if f and os.path.isfile(f)]
    
    if not valid_files:
        print(f"❌ No valid audio files to combine")
        return False
    
    print(f"\n📻 Combining {len(valid_files)} audio segments...")
    
    concat_txt = os.path.join(os.path.dirname(output_path), "audio_concat.txt")
    with open(concat_txt, "w", encoding="utf-8", newline='\n') as f:
        for audio_file in audio_files:
            if audio_file and os.path.isfile(audio_file):
                absolute_path = os.path.abspath(audio_file)
                safe_path = absolute_path.replace('\\', '/')
                safe_path = safe_path.replace("'", "\\'")
                f.write(f"file '{safe_path}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", output_path]
    try:
        print(f"   Running: ffmpeg concat...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            print(f"✅ Combined audio ({os.path.getsize(output_path) / (1024*1024):.1f} MB): {output_path}")
            return True
    except subprocess.CalledProcessError as e:
        print(f"   ⚠️  Concat copy failed, trying with re-encode...")
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
               "-c:a", "libmp3lame", "-q:a", "2", output_path]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                print(f"✅ Combined audio (re-encoded) ({os.path.getsize(output_path) / (1024*1024):.1f} MB): {output_path}")
                return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to combine audio files")
            print(f"   Error: {e.stderr}")
            return False
    
    print(f"❌ Failed to combine audio files")
    return False


def mux_audio_to_video(video_path, audio_path, output_path):
    """Mux the narration audio into the video file."""
    if not os.path.isfile(video_path):
        print(f"❌ Video file not found: {video_path}")
        return False
    
    if not os.path.isfile(audio_path):
        print(f"❌ Audio file not found: {audio_path}")
        return False
    
    print(f"\n🎧 Muxing audio into video...")
    print(f"   Video: {os.path.getsize(video_path) / (1024*1024):.1f} MB")
    print(f"   Audio: {os.path.getsize(audio_path) / (1024*1024):.1f} MB")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v:0",
        "-map", "1:a:0",
        output_path
    ]
    try:
        print(f"   Running: ffmpeg mux...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            print(f"✅ Muxed video with audio ({os.path.getsize(output_path) / (1024*1024):.1f} MB)")
            return True
        else:
            print(f"❌ Mux output file is invalid")
            return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to mux audio and video")
        print(f"   Error: {e.stderr}")
        return False


def render_frames(rows, narratives, durations):
    """Render image frames with text overlays and audio-based durations."""
    frames = []

    print(f"\n🎬 Creating intro frame...")
    intro_frames = [create_intro_frame(THEME_TITLE, THEME_SUBTITLE)] * int(max(INTRO_DURATION, durations[0]) * FPS)
    frames.extend(intro_frames)

    print(f"🎬 Processing {len(rows)} images with narrative text...")
    for idx, row in enumerate(rows):
        if idx % 10 == 0:
            print(f"   {idx+1}/{len(rows)}")

        image_data = get_image_blob(row)
        if image_data is None:
            continue

        narrative = narratives[idx + 1]
        frame = create_frame_with_text(image_data, narrative, idx, len(rows))
        frame_count = int(max(IMAGE_SEC, durations[idx + 1]) * FPS)
        frames.extend([frame] * frame_count)

    print(f"🎬 Creating outro frame...")
    outro_frames = [create_outro_frame(THEME_TITLE)] * int(max(OUTRO_DURATION, durations[-1]) * FPS)
    frames.extend(outro_frames)

    print(f"   Total frames: {len(frames)}")
    return frames


def create_intro_frame(title, subtitle):
    """Create an intro frame with title text."""
    bg = Image.new('RGB', (WIDTH, HEIGHT), (10, 10, 30))  # Dark blue
    draw = ImageDraw.Draw(bg)
    
    try:
        title_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 72)
        subtitle_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 42)
    except:
        title_font = subtitle_font = ImageFont.load_default()
    
    # Draw title
    title_y = HEIGHT // 3
    title_bbox = draw.textbbox((0, title_y), title, font=title_font)
    title_x = (WIDTH - (title_bbox[2] - title_bbox[0])) // 2
    draw.text((title_x, title_y), title, fill=(255, 215, 0), font=title_font)
    
    # Draw subtitle
    subtitle_y = title_y + 120
    subtitle_bbox = draw.textbbox((0, subtitle_y), subtitle, font=subtitle_font)
    subtitle_x = (WIDTH - (subtitle_bbox[2] - subtitle_bbox[0])) // 2
    draw.text((subtitle_x, subtitle_y), subtitle, fill=(200, 200, 200), font=subtitle_font)
    
    return np.array(bg)


def create_outro_frame(title):
    """Create an outro frame with closing text."""
    bg = Image.new('RGB', (WIDTH, HEIGHT), (10, 10, 30))  # Dark blue
    draw = ImageDraw.Draw(bg)
    
    try:
        title_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 56)
        text_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 40)
    except:
        title_font = text_font = ImageFont.load_default()
    
    # Draw main message
    messages = [
        "The spirit of exploration lives on.",
        "Every day, new frontiers await.",
        "What will you discover?"
    ]
    
    y_pos = HEIGHT // 3
    for msg in messages:
        bbox = draw.textbbox((0, y_pos), msg, font=text_font)
        x_pos = (WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x_pos, y_pos), msg, fill=(255, 215, 0), font=text_font)
        y_pos += 100
    
    return np.array(bg)


def main():
    parser = argparse.ArgumentParser(
        description=f"Create a themed viral video: {THEME_TITLE}"
    )
    parser.add_argument("--category", default="Exploration",
                       help="Image category to use (default: Exploration)")
    parser.add_argument("--total", type=int, default=85,
                       help="Number of images to use (default: 85 for ~20min)")
    parser.add_argument("--db", default=DEFAULT_DB,
                       help=f"Database path (default: {DEFAULT_DB})")
    parser.add_argument("--table", default=DEFAULT_TABLE,
                       help=f"Table name (default: {DEFAULT_TABLE})")
    parser.add_argument("--outdir", default="themed_video_output",
                       help="Output directory (default: themed_video_output)")
    parser.add_argument("--voice", default=DEFAULT_VOICE,
                       help="TTS voice to use for narration")
    parser.add_argument("--skip-audio", action="store_true",
                       help="Skip TTS audio generation")
    parser.add_argument("--list-categories", action="store_true",
                       help="List available categories and exit")

    args = parser.parse_args()

    # Check database exists
    if not os.path.isfile(args.db):
        print(f"❌ Database not found: {args.db}")
        sys.exit(1)

    # Print available categories if requested
    if args.list_categories:
        categories = get_available_categories(args.db, args.table)
        print("📂 Available categories:")
        for cat in categories:
            print(f"   - {cat}")
        sys.exit(0)

    # Create output directory
    os.makedirs(args.outdir, exist_ok=True)

    print(f"\n{'='*80}")
    print(f"🎥 Creating Themed Viral Video")
    print(f"{'='*80}")
    print(f"📽️  Theme:    {THEME_TITLE}")
    print(f"📂 Category: {args.category}")
    print(f"🖼️  Total images: {args.total}")
    print(f"🎙️  Voice:    {args.voice if not args.skip_audio else 'None (audio skipped)'}")
    print(f"⏱️  Duration: ~20 minutes (approx)")
    print(f"💾 Output:   {args.outdir}")
    print(f"{'='*80}\n")

    # Query images by category
    print(f"🔍 Querying database for '{args.category}' images...")
    rows = get_images_by_category(args.db, args.table, args.category, args.total)

    if not rows:
        print(f"❌ No images found for category '{args.category}'")
        print(f"\n💡 Available categories:")
        categories = get_available_categories(args.db, args.table)
        for cat in categories:
            print(f"   - {cat}")
        sys.exit(1)

    print(f"✅ Found {len(rows)} images\n")

    narratives = [generate_intro_text()]

    # Generate specific narratives using the row metadata for each image
    for idx, row in enumerate(rows):
        narrative = build_specific_narrative(row, args.category)
        narratives.append(narrative)

    narratives.append(generate_outro_text())

    durations = [INTRO_DURATION] + [IMAGE_SEC] * len(rows) + [OUTRO_DURATION]
    audio_path = None

    if not args.skip_audio:
        if HAS_EDGE_TTS:
            audio_dir = os.path.join(args.outdir, "audio_narration")
            audio_files, durations = create_narration_audio(narratives, audio_dir, voice=args.voice)
            
            # Count successful audio files
            valid_audio_files = [f for f in audio_files if f and os.path.isfile(f)]
            
            if valid_audio_files:
                combined_audio = os.path.join(args.outdir, "narration_combined.mp3")
                if combine_audio_files(audio_files, combined_audio):
                    audio_path = combined_audio
                else:
                    print("⚠️  Audio generated but failed to combine. Video will be silent.")
            else:
                print("⚠️  Failed to generate any audio. Video will be silent.")
        else:
            print("\n⚠️  edge-tts is not installed. Install with: pip install edge-tts")
            print("    Video will be created without narration audio.")
    else:
        print("\n⏭️  Audio generation skipped")

    print(f"\n🎬 Rendering video frames...")
    frames = render_frames(rows, narratives, durations)

    output_path = os.path.join(args.outdir, "themed_viral_video.mp4")
    print(f"\n🎞️  Writing video to {output_path}...")

    try:
        writer = imageio.get_writer(output_path, fps=FPS, codec='libx264', pixelformat='yuv420p')
        for i, frame in enumerate(frames):
            if i and i % 500 == 0:
                print(f"   {i}/{len(frames)} frames")
            writer.append_data(frame)
        writer.close()
        print(f"✅ Video created successfully!")
        print(f"   Duration: {len(frames) / FPS:.1f} seconds ({len(frames) / FPS / 60:.1f} minutes)")
        print(f"   Size: {os.path.getsize(output_path) / (1024*1024):.1f} MB")
    except Exception as e:
        print(f"❌ Error writing video: {e}")
        sys.exit(1)

    if audio_path:
        muxed_output = os.path.join(args.outdir, "themed_viral_video_with_voice.mp4")
        if mux_audio_to_video(output_path, audio_path, muxed_output):
            print(f"✅ Voice-enhanced video ready: {muxed_output}")
        else:
            print("⚠️  Failed to mux voice into video. The silent video is still available.")
    else:
        print("\n⚠️  No audio track available. Video will be silent.")

    print(f"\n{'='*80}")
    print(f"✨ Video ready!")
    if audio_path:
        print(f"   🎬 Silent video: {output_path}")
        print(f"   🎧 With voice:  {muxed_output}")
    else:
        print(f"   🎬 Silent video: {output_path}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
