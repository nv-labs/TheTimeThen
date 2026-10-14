#!/usr/bin/env python3
"""Create one 45-second vertical social video from themed database images.

The output is suitable for Instagram Reels, Facebook Reels, and YouTube
Shorts: 1080x1920 portrait MP4 at 30 fps.  It starts with a one-second
TheTimeThen title card followed by 11 distinct themed photos at four seconds
each (1 + 11 * 4 = 45 seconds).

Examples:
    python create_theme_short.py --theme "old cars"
    python create_theme_short.py --theme "old cars" --logo assets/logo.png
    python create_theme_short.py --theme "steam trains" --output out/trains.mp4
"""

import argparse
import io
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


WIDTH, HEIGHT, FPS = 1080, 1920, 30
INTRO_SECONDS = 1
IMAGE_SECONDS = 4
IMAGE_COUNT = 11
DEFAULT_DATABASES = ("image_collection.db", "universal_image_archive.db")
DEFAULT_MUSIC = Path("VideoAssets") / "Andres Jacque - Skipping [Thematic].mp3"
BLOB_COLUMNS = ("file_data", "image_data", "image", "photo_data", "data")
TEXT_COLUMNS = (
    "description", "xml_title", "xml_subject", "title", "subject",
    "category", "filename", "file_name", "source_url", "tags", "caption",
)
# These fields identify the individual photograph.  Category/subject/source
# fields are useful for browsing but are too broad to prove that the picture
# itself matches a theme (for example, an unrelated photo in a "cars" page).
DIRECT_PHOTO_COLUMNS = ("description", "xml_title", "title", "caption", "filename", "file_name", "tags")
THEME_FILLER_WORDS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "of", "on",
    "the", "to", "with", "old", "photo", "photos", "picture", "pictures",
    "image", "images", "vintage", "historic", "historical",
}


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({quote_identifier(table)})")}


def theme_terms(theme: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9]+", theme.lower())
    return [term for term in terms if len(term) >= 3 and term not in THEME_FILLER_WORDS]


def candidate_tables(connection: sqlite3.Connection) -> list[str]:
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [row[0] for row in tables]


def text_for_caption(row: sqlite3.Row) -> str:
    """Choose the most descriptive stored text for the on-image caption."""
    for field in ("description", "xml_title", "title", "caption", "filename", "file_name"):
        value = row[field] if field in row.keys() else None
        if value and str(value).strip():
            text = re.sub(r"[_-]+", " ", str(value)).strip()
            text = re.sub(r"\.(?:jpe?g|png|webp|gif)$", "", text, flags=re.IGNORECASE)
            return re.sub(r"\s+", " ", text)
    return ""


def matches_theme_fields(row: sqlite3.Row, fields: list[str], terms: list[str]) -> bool:
    """Require complete theme words in direct photo metadata.

    SQLite ``LIKE '%car%'`` also matches words such as ``Carter`` and
    ``Carousel``.  Validate candidate records in Python with word boundaries
    to prevent that kind of off-theme selection.
    """
    text = " ".join(str(row[field] or "") for field in fields).lower()
    for term in terms:
        variants = [term]
        if term.endswith("s") and len(term) > 3:
            variants.append(term[:-1])
        if not any(re.search(rf"\b{re.escape(variant)}\b", text) for variant in variants):
            return False
    return True


def search_database(db_path: Path, theme: str, needed: int) -> list[dict]:
    """Return matching image records without loading unrelated image BLOBs."""
    if not db_path.exists():
        print(f"Skipping missing database: {db_path}")
        return []

    terms = theme_terms(theme) or [theme.lower()]
    matches: list[dict] = []
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        for table in candidate_tables(connection):
            columns = table_columns(connection, table)
            blob_column = next((name for name in BLOB_COLUMNS if name in columns), None)
            searchable = [name for name in TEXT_COLUMNS if name in columns]
            direct_fields = [name for name in DIRECT_PHOTO_COLUMNS if name in columns]
            id_column = "id" if "id" in columns else "rowid"
            if not blob_column or not searchable or not direct_fields:
                continue

            # Every meaningful word must occur in some searchable field. For
            # example, "old cars" searches for "cars" (not the unhelpfully
            # broad word "old") and avoids pulling unrelated archive images.
            where_parts = []
            parameters = []
            # Matching is intentionally restricted to photo-specific fields;
            # do not accept a hit only in generic category or source metadata.
            text_expression = " || ' ' || ".join(
                f"COALESCE({quote_identifier(column)}, '')" for column in direct_fields
            )
            selected_text = ", ".join(
                f"{quote_identifier(column)} AS {quote_identifier(column)}" for column in direct_fields
            )
            for term in terms:
                # Let a plural theme find singular metadata too: "old cars"
                # should match descriptions containing either "car" or
                # "cars".
                variants = [term]
                if term.endswith("s") and len(term) > 3:
                    variants.append(term[:-1])
                where_parts.append(
                    "(" + " OR ".join(f"LOWER({text_expression}) LIKE ?" for _ in variants) + ")"
                )
                parameters.extend(f"%{variant}%" for variant in variants)

            sql = f"""
                SELECT {quote_identifier(id_column)} AS record_id,
                       {quote_identifier('filename') if 'filename' in columns else "''"} AS filename,
                       {selected_text}
                FROM {quote_identifier(table)}
                WHERE {' AND '.join(where_parts)}
                ORDER BY {quote_identifier(id_column)} DESC
                LIMIT ?
            """
            # Get a modest candidate pool, then apply exact whole-word
            # matching below.  SQL LIKE is only the fast first pass.
            rows = connection.execute(sql, (*parameters, needed * 20)).fetchall()
            for row in rows:
                if matches_theme_fields(row, direct_fields, terms):
                    blob_row = connection.execute(
                        f"SELECT {quote_identifier(blob_column)} FROM {quote_identifier(table)} "
                        f"WHERE {quote_identifier(id_column)} = ?",
                        (row["record_id"],),
                    ).fetchone()
                    if not blob_row or not blob_row[0]:
                        continue
                    matches.append({
                        "database": str(db_path),
                        "table": table,
                        "id": row["record_id"],
                        "filename": row["filename"] or f"{table}:{row['record_id']}",
                        "caption": text_for_caption(row),
                        "blob": blob_row[0],
                    })
                    if len(matches) >= needed:
                        break
            if len(matches) >= needed:
                break
    finally:
        connection.close()

    random.shuffle(matches)
    return matches[:needed]


def find_images(databases: list[Path], theme: str) -> list[dict]:
    selected: list[dict] = []
    for database in databases:
        remaining = IMAGE_COUNT - len(selected)
        if remaining <= 0:
            break
        found = search_database(database, theme, remaining)
        selected.extend(found)
        print(f"{database}: found {len(found)} matching image(s)")
    return selected


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def cover_image(image: Image.Image) -> Image.Image:
    """Centre-crop an image to fill a 9:16 social-video frame."""
    return ImageOps.fit(image.convert("RGB"), (WIDTH, HEIGHT), Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def title_card(logo_path: Path | None) -> np.ndarray:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#080b12")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, WIDTH, 18), fill="#d2a550")

    if logo_path:
        with Image.open(logo_path) as logo:
            logo = logo.convert("RGBA")
            logo.thumbnail((760, 760), Image.Resampling.LANCZOS)
            x = (WIDTH - logo.width) // 2
            y = (HEIGHT - logo.height) // 2 - 70
            canvas.paste(logo, (x, y), logo)
    else:
        brand = "THE TIME THEN"
        brand_font = font(94)
        subtitle_font = font(32)
        brand_box = draw.textbbox((0, 0), brand, font=brand_font)
        draw.text(((WIDTH - (brand_box[2] - brand_box[0])) / 2, HEIGHT / 2 - 95), brand,
                  font=brand_font, fill="#f1e6cf")
        subtitle = "HISTORY IN PICTURES"
        subtitle_box = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        draw.text(((WIDTH - (subtitle_box[2] - subtitle_box[0])) / 2, HEIGHT / 2 + 35), subtitle,
                  font=subtitle_font, fill="#d2a550")

    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


def image_frame(blob: bytes, caption: str) -> np.ndarray:
    with Image.open(io.BytesIO(blob)) as image:
        frame = cover_image(image)
    draw = ImageDraw.Draw(frame, "RGBA")
    caption = (caption or "").strip()
    if caption:
        caption = textwrap.shorten(caption, width=130, placeholder="…")
        caption_font = font(42)
        lines = textwrap.wrap(caption, width=38)[:3]
        line_height = 54
        band_height = 44 + len(lines) * line_height
        draw.rectangle((0, HEIGHT - band_height, WIDTH, HEIGHT), fill=(0, 0, 0, 175))
        y = HEIGHT - band_height + 22
        for line in lines:
            box = draw.textbbox((0, 0), line, font=caption_font)
            draw.text(((WIDTH - (box[2] - box[0])) / 2, y), line, font=caption_font, fill="white")
            y += line_height
    return cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2BGR)


def write_repeated(writer: cv2.VideoWriter, frame: np.ndarray, seconds: int) -> None:
    for _ in range(seconds * FPS):
        writer.write(frame)


def add_background_music(video_path: Path, music_path: Path) -> None:
    """Loop and mux music for the complete 45-second final video."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        windows_ffmpeg = Path(r"C:\ffmpeg-8.0.1-essentials_build\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe")
        if windows_ffmpeg.is_file():
            ffmpeg = str(windows_ffmpeg)
    if not ffmpeg:
        raise RuntimeError("ffmpeg was not found. Install it or add it to PATH to add background music.")
    temporary_output = video_path.with_name(f"{video_path.stem}_with_music.mp4")
    command = [
        ffmpeg, "-y", "-i", str(video_path), "-stream_loop", "-1", "-i", str(music_path),
        "-filter:a", "volume=0.18", "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", "45",
        "-shortest", str(temporary_output),
    ]
    subprocess.run(command, check=True)
    temporary_output.replace(video_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one themed 45-second vertical social video.")
    parser.add_argument("--theme", required=True, help='Theme to match, for example: "old cars"')
    parser.add_argument("--db", action="append", dest="databases", help="Database to search; repeat to search more than one.")
    parser.add_argument("--logo", type=Path, help="Optional PNG/JPG TheTimeThen logo. A text logo is used when omitted.")
    parser.add_argument("--music", type=Path, default=DEFAULT_MUSIC, help="Background MP3/WAV for the full 45 seconds.")
    parser.add_argument("--output", type=Path, default=Path("out/theme_short.mp4"), help="Output MP4 path.")
    args = parser.parse_args()

    if args.logo and not args.logo.is_file():
        parser.error(f"Logo file not found: {args.logo}")
    if not args.music.is_file():
        parser.error(f"Music file not found: {args.music}")

    database_paths = [Path(path) for path in (args.databases or DEFAULT_DATABASES)]
    records = find_images(database_paths, args.theme)
    if len(records) < IMAGE_COUNT:
        print(f"Only found {len(records)} distinct image(s) for theme {args.theme!r}; need {IMAGE_COUNT}.", file=sys.stderr)
        return 2

    frames = []
    for record in records:
        try:
            frames.append(image_frame(record["blob"], record["caption"]))
        except Exception as error:
            print(f"Skipping unreadable image {record['filename']}: {error}", file=sys.stderr)
    if len(frames) < IMAGE_COUNT:
        print(f"Only {len(frames)} matching images could be decoded; need {IMAGE_COUNT}.", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(args.output), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT)
    )
    if not writer.isOpened():
        print("Could not initialise the MP4 writer. Ensure OpenCV video codecs are installed.", file=sys.stderr)
        return 1

    try:
        write_repeated(writer, title_card(args.logo), INTRO_SECONDS)
        for frame in frames[:IMAGE_COUNT]:
            write_repeated(writer, frame, IMAGE_SECONDS)
    finally:
        writer.release()

    try:
        add_background_music(args.output, args.music)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"Video was created but music could not be added: {error}", file=sys.stderr)
        return 1

    print(f"Created {args.output} — 45 seconds, {IMAGE_COUNT} themed photos, captions, and music.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
