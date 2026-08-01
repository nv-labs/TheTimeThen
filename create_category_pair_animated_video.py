#!/usr/bin/env python3
"""Create a 2-photo category video with AI narration and animated motion.

This script:
1. Finds two images from the same category in image_collection.db / image_comp
2. Analyzes the actual DB image bytes for scene context instead of text-based web search
3. Builds a vivid, context-specific spoken narration prompt for each image
4. Writes a 5-second static photo segment and a 15-second animated motion segment
5. Optionally generates edge-tts narration audio if installed
6. Saves final video and audio artifacts to the output folder

Usage:
    python create_category_pair_animated_video.py --outdir pair_video
    python create_category_pair_animated_video.py --category "Exploration" --outdir pair_video
"""

import argparse
import base64
import io
import math
import os
import random
import re
import sqlite3
import subprocess
import sys
import textwrap
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("❌ Pillow is required. Install with: pip install pillow")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("❌ numpy is required. Install with: pip install numpy")
    sys.exit(1)

try:
    import imageio
except ImportError:
    print("❌ imageio is required. Install with: pip install imageio")
    sys.exit(1)

HAS_EDGE_TTS = False
try:
    import asyncio
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    pass

HAS_OPENAI = False
try:
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        client = OpenAI(api_key=api_key)
        HAS_OPENAI = True
except Exception:
    HAS_OPENAI = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "image_collection.db")
TABLE_NAME = "image_comp"
WIDTH = 1920
HEIGHT = 1088
FPS = 24
STATIC_SECONDS = 5
ANIMATED_SECONDS = 15
MIN_TOTAL_DURATION_SECONDS = 65
SPEECH_PADDING_SECONDS = 2.0
WORD_GOAL = 70
DEFAULT_BG_MUSIC = os.path.join(BASE_DIR, "VideoAssets", "Andres Jacque - Skipping [Thematic].mp3")
DEFAULT_OUTPUT_DIR = r"D:\Dev\ImkerijKeiberg\pair_video"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def find_ffmpeg() -> str:
    for candidate in ["ffmpeg", r"C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe", r"C:\\ffmpeg\\bin\\ffmpeg.exe"]:
        if shutil_which(candidate):
            return candidate
    raise RuntimeError("ffmpeg not found. Install FFmpeg and put it in PATH")


def shutil_which(program):
    try:
        import shutil
        return shutil.which(program)
    except Exception:
        return None


def db_connect(db_path: str):
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def choose_category(conn, requested_category=None):
    cur = conn.cursor()
    if requested_category:
        cur.execute(
            f"SELECT xml_subject, COUNT(*) AS c FROM {TABLE_NAME} WHERE xml_subject = ? GROUP BY xml_subject",
            (requested_category,),
        )
        row = cur.fetchone()
        if row and row[1] >= 2:
            return requested_category
        raise ValueError(f"Category '{requested_category}' not found with at least 2 images")

    cur.execute(
        f"SELECT xml_subject, COUNT(*) AS c FROM {TABLE_NAME} GROUP BY xml_subject HAVING COUNT(*) >= 2 ORDER BY c DESC"
    )
    rows = cur.fetchall()
    if not rows:
        raise ValueError("No category has at least two images")
    return rows[0][0]


def get_two_images(conn, category):
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, file_data, xml_subject, description, xml_title FROM {TABLE_NAME} "
        "WHERE xml_subject = ? ORDER BY RANDOM() LIMIT 2",
        (category,),
    )
    rows = cur.fetchall()
    if len(rows) < 2:
        raise ValueError(f"Found only {len(rows)} images in category '{category}'")
    return rows


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def image_to_data_url(image_bytes: bytes) -> str:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            mime_type = img.get_format_mimetype() or "image/jpeg"
    except Exception:
        mime_type = "image/jpeg"
    return f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"


def analyze_image_context(image_bytes: bytes, description: str, category: str, index: int) -> str:
    if not HAS_OPENAI:
        return (
            f"Category: {category}\n"
            f"Description: {description}\n"
            "Context note: focus on the era, setting, social atmosphere, and historical significance visible in the image."
        )

    try:
        prompt = textwrap.dedent(
            f"""
            You are analyzing a historical photograph for a documentary-style video narration.
            Look at the actual image and identify the specific context it suggests:
            - place, era, or moment in history
            - atmosphere, people, or social setting
            - why this image matters beyond the obvious subject

            Also use this metadata for extra grounding:
            Category: {category}
            Description: {description}

            Write 3 short bullet points that are concrete and context-rich.
            Avoid generic lines like "a woman in a dress" or "a photo of people".
            Focus on the scene's historical, cultural, or emotional significance.
            """
        ).strip()

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_to_data_url(image_bytes)}}
                    ],
                }
            ],
            temperature=0.5,
            max_tokens=120,
        )
        content = response.choices[0].message.content or ""
        return clean_text(content.strip())
    except Exception as exc:
        print(f"⚠️ Image analysis failed: {exc}")
        return (
            f"Category: {category}\n"
            f"Description: {description}\n"
            "Context note: focus on the setting, mood, and historical significance of the scene."
        )


def generate_narration_text(image_bytes: bytes, description: str, category: str, index: int):
    image_context = analyze_image_context(image_bytes, description, category, index)

    template = textwrap.dedent(
        """
        You are writing a vivid spoken narration for a short documentary-style video segment.
        Write 65-85 words, conversational and precise, and make the line sound like it belongs to the
        historical setting of the image rather than a generic photo caption.
        Use the actual image analysis and metadata to emphasize the era, place, atmosphere, and cultural or
        historical significance of the scene.
        Avoid vague wording such as “a woman in a dress” or “a photo of people.”
        Output only the narration text.
        """
    ).strip()

    prompt = (
        f"{template}\n\n"
        f"Image #{index + 1}\n"
        f"Category: {category}\n"
        f"Description: {description}\n\n"
        f"Image context notes:\n{image_context}\n\n"
        f"Make the narration specific to the scene’s context and easy to speak aloud."
    )

    if not HAS_OPENAI:
        fallback = (
            f"This {category.lower()} image shows {description}. It invites us to pause, reflect, "
            f"and imagine the story behind the scene."
        )
        return clean_text(fallback)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=120,
        )
        content = response.choices[0].message.content or ""
        narration = clean_text(content.strip())
        if len(narration.split()) < 30:
            narration = f"{description}. {narration}"
        return narration
    except Exception as exc:
        print(f"⚠️ OpenAI narration failed: {exc}")
        return clean_text(
            f"This {category.lower()} image shows {description}. It invites us to explore its story and the world behind it."
        )


async def generate_speech(text: str, output_path: str, voice="en-US-AriaNeural") -> bool:
    if not HAS_EDGE_TTS:
        return False
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(output_path)
        return True
    except Exception as exc:
        print(f"❌ edge-tts error: {exc}")
        return False


def save_audio(text: str, output_path: str) -> bool:
    if not HAS_EDGE_TTS:
        return False
    try:
        import asyncio
        return asyncio.run(generate_speech(text, output_path))
    except Exception as exc:
        print(f"❌ Audio generation failed: {exc}")
        return False


def render_static_frame(image_bytes: bytes, caption: str) -> np.ndarray:
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        img.thumbnail((WIDTH * 0.92, HEIGHT * 0.78), Image.Resampling.LANCZOS)
        bg = Image.new("RGB", (WIDTH, HEIGHT), (16, 18, 32))
        paste_x = (WIDTH - img.width) // 2
        paste_y = (HEIGHT - img.height) // 2
        bg.paste(img, (paste_x, paste_y))

        draw = ImageDraw.Draw(bg)
        try:
            font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 36)
        except Exception:
            font = ImageFont.load_default()

        text = clean_text(caption)
        if text:
            lines = textwrap.wrap(text, 60)
            bar_h = len(lines) * 44 + 36
            overlay = Image.new("RGBA", (WIDTH, bar_h), (0, 0, 0, 180))
            bar_draw = ImageDraw.Draw(overlay)
            y = 18
            for line in lines:
                bar_draw.text((40, y), line, font=font, fill=(240, 240, 240))
                y += 44
            bg.paste(overlay, (0, HEIGHT - bar_h), overlay)

        return np.array(bg)


def render_animated_frames(image_bytes: bytes, caption: str, frame_count: int) -> list[np.ndarray]:
    with Image.open(io.BytesIO(image_bytes)) as src_img:
        src = src_img.convert("RGB")
        src = src.resize((WIDTH, int(WIDTH * src.height / src.width)), Image.Resampling.LANCZOS) if src.width > src.height else src.resize((int(HEIGHT * src.width / src.height), HEIGHT), Image.Resampling.LANCZOS)

        frames = []
        for frame_index in range(frame_count):
            progress = frame_index / max(frame_count - 1, 1)
            scale = 1.0 + 0.04 * math.sin(progress * math.pi * 2)
            angle = 0.0

            w = int(src.width * scale)
            h = int(src.height * scale)
            frame_img = src.resize((w, h), Image.Resampling.LANCZOS)

            bg = Image.new("RGB", (WIDTH, HEIGHT), (12, 14, 26))
            offset_x = int((WIDTH - w) / 2 + math.sin(progress * math.pi * 2) * 40)
            offset_y = int((HEIGHT - h) / 2 + math.cos(progress * math.pi * 2) * 20)
            bg.paste(frame_img, (offset_x, offset_y))

            overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            glow = int(80 + 40 * abs(math.sin(progress * math.pi)))
            overlay_draw.rectangle([0, 0, WIDTH, HEIGHT], fill=(0, 0, 0, glow))
            bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

            draw = ImageDraw.Draw(bg)
            try:
                title_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 38)
            except Exception:
                title_font = ImageFont.load_default()

            caption_lines = textwrap.wrap(clean_text(caption), width=55)
            text_y = HEIGHT - 180
            for line in caption_lines[-3:]:
                text_bbox = draw.textbbox((0, 0), line, font=title_font)
                draw.rectangle(
                    [30, text_y - 10, 30 + text_bbox[2] + 20, text_y + text_bbox[3] + 10],
                    fill=(0, 0, 0, 180),
                )
                draw.text((40, text_y), line, fill=(255, 255, 255), font=title_font)
                text_y += text_bbox[3] + 14

            frames.append(np.array(bg))

        return frames


def write_video(frames: list[np.ndarray], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with imageio.get_writer(output_path, fps=FPS, codec="libx264", quality=8, macro_block_size=1) as writer:
        for index, frame in enumerate(frames):
            writer.append_data(frame)  # type: ignore[attr-defined]
    return output_path


def combine_audio_video(video_path: str, audio_path: str, output_path: str) -> bool:
    ffmpeg = shutil_which("ffmpeg")
    if not ffmpeg:
        print("⚠️ ffmpeg not found; cannot combine audio and video automatically.")
        return False
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                video_path,
                "-i",
                audio_path,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ ffmpeg combine error: {exc.stderr.decode(errors='ignore')}")
        return False


def probe_duration_seconds(media_path: str) -> float | None:
    ffprobe = shutil_which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                media_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        value = (result.stdout or "").strip()
        if not value:
            return None
        return float(value)
    except Exception:
        return None


def extend_video_to_duration(video_path: str, target_duration: float, output_path: str) -> bool:
    ffmpeg = shutil_which("ffmpeg")
    if not ffmpeg:
        print("⚠️ ffmpeg not found; cannot extend video duration automatically.")
        return False
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                video_path,
                "-filter_complex",
                f"[0:v]tpad=stop_mode=clone:stop_duration={max(0.0, target_duration):.3f}[v]",
                "-map",
                "[v]",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "aac",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ ffmpeg extend error: {exc.stderr.decode(errors='ignore')}")
        return False


def mix_narration_with_background_music(
    narration_path: str, music_path: str, output_path: str, music_volume: float = 0.14
) -> bool:
    ffmpeg = shutil_which("ffmpeg")
    if not ffmpeg:
        print("⚠️ ffmpeg not found; cannot mix background music.")
        return False
    if not os.path.exists(music_path):
        print(f"⚠️ Background music file not found: {music_path}")
        return False

    narration_duration = probe_duration_seconds(narration_path)
    if narration_duration is None:
        print("⚠️ Could not detect narration duration; skipping music mix.")
        return False

    # Loop music and keep it soft under narration for intelligibility.
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                narration_path,
                "-stream_loop",
                "-1",
                "-i",
                music_path,
                "-filter_complex",
                (
                    "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.0[a0];"
                    f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                    f"atrim=0:{narration_duration:.3f},volume={music_volume:.3f}[a1];"
                    "[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                ),
                "-map",
                "[aout]",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ ffmpeg music mix error: {exc.stderr.decode(errors='ignore')}")
        return False


def remove_time_window(video_path: str, output_path: str, start_sec: float, end_sec: float) -> bool:
    ffmpeg = shutil_which("ffmpeg")
    if not ffmpeg:
        print("⚠️ ffmpeg not found; cannot remove a time window.")
        return False
    if end_sec <= start_sec:
        print("⚠️ Invalid remove window; skipping.")
        return False
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                video_path,
                "-filter_complex",
                (
                    f"[0:v]trim=0:{start_sec},setpts=PTS-STARTPTS[v0];"
                    f"[0:v]trim=start={end_sec},setpts=PTS-STARTPTS[v1];"
                    f"[0:a]atrim=0:{start_sec},asetpts=PTS-STARTPTS[a0];"
                    f"[0:a]atrim=start={end_sec},asetpts=PTS-STARTPTS[a1];"
                    "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
                ),
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "aac",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"❌ ffmpeg remove-window error: {exc.stderr.decode(errors='ignore')}")
        return False


def build_segment(image_row, index, outdir, generate_audio=True):
    image_id = image_row["id"]
    description = clean_text(image_row["description"] or image_row["xml_title"] or "A historic photo")
    category = clean_text(image_row["xml_subject"] or "Unknown")
    title = clean_text(image_row["xml_title"] or category)

    narration = generate_narration_text(image_row["file_data"], description, category, index)

    segment_name = f"segment_{index + 1}"
    segment_dir = os.path.join(outdir, segment_name)
    os.makedirs(segment_dir, exist_ok=True)

    audio_path = os.path.join(segment_dir, f"narration_{index + 1}.mp3")
    audio_created = False
    if generate_audio:
        audio_created = save_audio(narration, audio_path)
        if not audio_created and HAS_EDGE_TTS:
            print(f"⚠️  Could not generate audio for segment {index + 1}")

    print(f"\n📷 Image {index + 1}: {title} ({category})")
    print(f"   Description: {description}")
    print(f"   Narration: {narration[:120]}...")

    static_frame = render_static_frame(image_row["file_data"], narration)
    narration_duration = probe_duration_seconds(audio_path) if audio_created else None
    target_segment_seconds = STATIC_SECONDS + ANIMATED_SECONDS
    if narration_duration is not None:
        # Keep segment long enough for full speech plus a tiny breathing buffer.
        target_segment_seconds = max(target_segment_seconds, int(narration_duration + SPEECH_PADDING_SECONDS))
    animated_seconds = max(ANIMATED_SECONDS, target_segment_seconds - STATIC_SECONDS)

    animated_frames = render_animated_frames(image_row["file_data"], narration, int(animated_seconds * FPS))
    static_frames = [static_frame] * int(STATIC_SECONDS * FPS)
    all_frames = static_frames + animated_frames

    segment_video = os.path.join(outdir, f"{segment_name}.mp4")
    write_video(all_frames, segment_video)
    return segment_video, audio_path if audio_created else None


def main():
    global TABLE_NAME
    parser = argparse.ArgumentParser(description="Create a category pair AI video with narration")
    parser.add_argument("--category", default=None, help="Use this exact category")
    parser.add_argument("--db", default=DB_PATH, help="Path to image_collection.db")
    parser.add_argument("--table", default=TABLE_NAME, help="Table name in database")
    parser.add_argument("--outdir", default=DEFAULT_OUTPUT_DIR, help="Output folder")
    parser.add_argument("--no-audio", action="store_true", help="Do not generate narration audio")
    parser.add_argument("--music", default=DEFAULT_BG_MUSIC, help="Background music file path")
    parser.add_argument("--music-volume", type=float, default=0.14, help="Background music volume (0.0-1.0)")
    parser.add_argument("--remove-start", type=float, default=3.0, help="Start second to cut from final output")
    parser.add_argument("--remove-end", type=float, default=6.0, help="End second to cut from final output")
    args = parser.parse_args()

    if args.table != TABLE_NAME:
        TABLE_NAME = args.table

    try:
        conn = db_connect(args.db)
        category = choose_category(conn, args.category)
        rows = get_two_images(conn, category)
        print(f"✅ Selected category '{category}' with {len(rows)} images")
    except Exception as exc:
        print(f"❌ Error selecting images: {exc}")
        sys.exit(1)

    os.makedirs(args.outdir, exist_ok=True)
    segment_files = []
    audio_files = []

    for index, row in enumerate(rows):
        video_file, audio_file = build_segment(row, index, args.outdir, generate_audio=not args.no_audio)
        segment_files.append(video_file)
        if audio_file:
            audio_files.append(audio_file)

    final_video = os.path.join(args.outdir, "category_pair_video.mp4")
    concat_txt = os.path.join(args.outdir, "segments.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for seg in segment_files:
            f.write(f"file '{os.path.abspath(seg).replace('\\', '/')}'\n")

    ffmpeg = shutil_which("ffmpeg")
    if not ffmpeg:
        print("⚠️  ffmpeg not found. You will need to combine segment MP4 files manually.")
        return

    try:
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", final_video],
            check=True,
            capture_output=True,
        )
        print(f"✅ Combined final video: {final_video}")
    except subprocess.CalledProcessError as exc:
        print(f"❌ ffmpeg concat error: {exc.stderr.decode(errors='ignore')}")
        sys.exit(1)

    if audio_files and not args.no_audio:
        combined_audio = os.path.join(args.outdir, "combined_narration.mp3")
        concat_audio = os.path.join(args.outdir, "audio_files.txt")
        with open(concat_audio, "w", encoding="utf-8") as f:
            for audio in audio_files:
                f.write(f"file '{os.path.abspath(audio).replace('\\', '/')}'\n")
        try:
            subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_audio, "-c", "copy", combined_audio],
                check=True,
                capture_output=True,
            )
            mixed_audio = os.path.join(args.outdir, "combined_narration_with_music.m4a")
            speech_audio = combined_audio
            if args.music and os.path.exists(args.music):
                if mix_narration_with_background_music(combined_audio, args.music, mixed_audio, args.music_volume):
                    speech_audio = mixed_audio
                    print(f"✅ Added soft background music: {args.music}")
                else:
                    print("⚠️ Failed to mix background music, continuing with narration only.")
            else:
                print(f"ℹ️ No background music file found at '{args.music}', narration-only output will be used.")

            narration_duration = probe_duration_seconds(speech_audio) or 0.0
            video_duration = probe_duration_seconds(final_video) or 0.0
            working_video = final_video
            if narration_duration > video_duration:
                extended_video = os.path.join(args.outdir, "category_pair_video_extended.mp4")
                if extend_video_to_duration(final_video, narration_duration - video_duration + 0.5, extended_video):
                    working_video = extended_video
                    print(
                        f"✅ Extended video to include full speech "
                        f"({video_duration:.1f}s -> {probe_duration_seconds(working_video) or video_duration:.1f}s)."
                    )
                else:
                    print("⚠️ Could not extend video; speech may end near the tail.")

            min_target = float(MIN_TOTAL_DURATION_SECONDS)
            current_duration = probe_duration_seconds(working_video) or 0.0
            if current_duration < min_target:
                min_extended_video = os.path.join(args.outdir, "category_pair_video_min_duration.mp4")
                if extend_video_to_duration(working_video, min_target - current_duration, min_extended_video):
                    working_video = min_extended_video
                    print(f"✅ Extended video to minimum target duration ({MIN_TOTAL_DURATION_SECONDS}s).")

            final_output = os.path.join(args.outdir, "category_pair_video_with_audio.mp4")
            if combine_audio_video(working_video, speech_audio, final_output):
                trimmed_output = os.path.join(args.outdir, "category_pair_video_with_audio_trimmed.mp4")
                if remove_time_window(final_output, trimmed_output, args.remove_start, args.remove_end):
                    final_output = trimmed_output
                    print(f"✅ Removed interval {args.remove_start:.1f}s-{args.remove_end:.1f}s from final output.")
                print(f"✅ Final output with narration and music: {final_output}")
            else:
                print(f"⚠️  Video created without combining audio: {final_video}")
        except subprocess.CalledProcessError as exc:
            print(f"❌ ffmpeg audio concat error: {exc.stderr.decode(errors='ignore')}")
    else:
        print("ℹ️  No narration audio files generated.")

    print("\n🎉 Done. Check the output folder for video and audio files.")


if __name__ == "__main__":
    main()
