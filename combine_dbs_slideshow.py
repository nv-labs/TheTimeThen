#!/usr/bin/env python3
"""
Combine images from two different SQLite DBs (schemas used by VideoCreation2.py
and VideoFromPhotosTable.py) into a single slideshow.

Usage example (single-line, pasteable into Windows cmd):
    python combine_dbs_slideshow.py --db1 d:/Dev/TheTimeThen/universal_image_archive.db --db1-table photos_2023_photos --db2 d:/Dev/TheTimeThen/image_collection.db --db2-table image_comp --total 35 --pct1 60 --outdir out

This will pick ~60% images from db1 and 40% from db2 (total 35 images), render
frames and write `combined_slideshow.mp4` in the output directory.

Options to mark used images with `VideoAirDate` are available with `--mark-used`.
"""
import argparse
import os
import sqlite3
import io
import random
from datetime import datetime
import textwrap
import subprocess
import shutil
import math
import concurrent.futures
import time
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import imageio
import ffmpeg

BASE = os.path.dirname(os.path.abspath(__file__))

# Defaults matching the other scripts
DEFAULT_DB1_TABLE = "photos_2023_photos"
DEFAULT_DB2_TABLE = "image_comp"
WIDTH, HEIGHT = 1920, 1088
FPS = 24
IMAGE_SEC = 14
INTRO_DURATION = 3.5
OUTRO_DURATION = 16


def add_stars(bg_img, num_stars=200, seed=None):
    """Add random white stars to the background image with optional seed for variation."""
    if seed is not None:
        random.seed(seed)
    w, h = bg_img.size
    draw = ImageDraw.Draw(bg_img)
    for _ in range(num_stars):
        x = random.randint(0, w)
        y = random.randint(0, h)
        size = random.randint(1, 2)
        opacity = random.randint(128, 255)
        draw.ellipse((x - size, y - size, x + size, y + size), fill=(255, 255, 255, opacity))
    return bg_img


def process_intro_outro_image(file_data, target_width, target_height, num_frames, fps, is_intro=False):
    """Process intro/outro image: resize to fit, center on starry background."""
    try:
        img = Image.open(file_data).convert('RGB')

        scale_factor = 1.25
        new_width = int(target_width * scale_factor)
        new_height = int(target_height * scale_factor)
        img.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)
        
        bg = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 255))
        
        if is_intro:
            bg = add_stars(bg, num_stars=200, seed=None)
            paste_x = (target_width - img.width) // 2
            paste_y = (target_height - img.height) // 2
            bg.paste(img, (paste_x, paste_y))
            single_frame = np.array(bg.convert('RGB'))
            frames = [single_frame] * num_frames
        else:
            frames = []
            for frame_idx in range(num_frames):
                bg = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 255))
                seed = frame_idx // 50
                bg = add_stars(bg, num_stars=200, seed=seed)
                paste_x = (target_width - img.width) // 2
                paste_y = (target_height - img.height) // 2
                bg.paste(img, (paste_x, paste_y))
                frames.append(np.array(bg.convert('RGB')))
        
        return frames
    except Exception as e:
        print(f"Error processing {'intro' if is_intro else 'outro'} image: {e}")
        return None


def ensure_airdate_column(conn, table):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if "VideoAirDate" not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN VideoAirDate TEXT")
        conn.commit()


def discover_table_columns(conn, table):
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return [r[1] for r in cur.fetchall()]
    except Exception:
        return []


def table_exists(conn, table):
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        return cur.fetchone() is not None
    except Exception:
        return False


def resolve_table_name(conn, preferred_table, fallback_tables=None):
    fallback_tables = fallback_tables or []
    if preferred_table and table_exists(conn, preferred_table):
        return preferred_table
    for candidate in fallback_tables:
        if candidate and table_exists(conn, candidate):
            return candidate
    return preferred_table


def resolve_table_columns(conn, table, preferred_title_col=None, preferred_blob_col="file_data"):
    cols = discover_table_columns(conn, table)
    if not cols:
        return None, None, None

    title_col = None
    for candidate in [preferred_title_col, "xml_title", "description", "title", "name", "caption", "text"]:
        if candidate and candidate in cols:
            title_col = candidate
            break

    blob_col = None
    for candidate in [preferred_blob_col, "file_data", "image_data", "data", "blob", "file_bytes", "image"]:
        if candidate and candidate in cols:
            blob_col = candidate
            break

    return table, blob_col, title_col


def fetch_images_from_table(db_path, table, id_col="id", blob_col="file_data", title_col=None, limit=100):
    """Fetch rows with empty VideoAirDate. Returns list of (id, blob_bytes, title_text).
    title_col may be None; then title_text will be ''"""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        ensure_airdate_column(conn, table)
    except Exception:
        # if table doesn't exist or other issue, return empty
        conn.close()
        return []

    cur = conn.cursor()
    title_select = f", {title_col}" if title_col else ""
    try:
        cur.execute(f"SELECT {id_col}, {blob_col}{title_select} FROM {table} WHERE VideoAirDate IS NULL OR VideoAirDate = '' ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
    except Exception:
        rows = []
    conn.close()

    out = []
    for r in rows:
        if title_col:
            pid, blob, title = r
            title = title or ""
        else:
            pid, blob = r
            title = ""
        out.append((pid, blob, title))
    return out


def intersperse_images(keyword_images, non_keyword_images, max_images=35, min_gap=2):
    """From VideoCreation2.py: intersperse keyword images evenly with non-keyword images."""
    result = []
    keyword_count = min(len(keyword_images), 5)
    non_keyword_count = len(non_keyword_images)
    total_images = min(keyword_count + non_keyword_count, max_images)
    if not keyword_images:
        random.shuffle(non_keyword_images)
        return non_keyword_images[:max_images]
    if not non_keyword_images:
        random.shuffle(keyword_images)
        return keyword_images[:max_images]
    random.shuffle(keyword_images)
    random.shuffle(non_keyword_images)
    if keyword_count > 0:
        step = max(min_gap, total_images // (keyword_count + 1))
        keyword_positions = [step * (i + 1) for i in range(keyword_count)]
        keyword_positions = [min(pos, total_images - 1) for pos in keyword_positions]
        for i in range(len(keyword_positions) - 1):
            if keyword_positions[i + 1] - keyword_positions[i] < min_gap:
                keyword_positions[i + 1] = keyword_positions[i] + min_gap
        keyword_positions = [pos for pos in keyword_positions if pos < total_images]
        keyword_count = len(keyword_positions)
    keyword_idx = 0
    non_keyword_idx = 0
    for i in range(total_images):
        if keyword_idx < keyword_count and i == keyword_positions[keyword_idx]:
            result.append(keyword_images[keyword_idx])
            keyword_idx += 1
        elif non_keyword_idx < non_keyword_count:
            result.append(non_keyword_images[non_keyword_idx])
            non_keyword_idx += 1
        elif keyword_idx < keyword_count:
            result.append(keyword_images[keyword_idx])
            keyword_idx += 1
    result = result[:max_images]
    while keyword_idx < keyword_count and len(result) < max_images:
        result.append(keyword_images[keyword_idx])
        keyword_idx += 1
    return result[:max_images]


def fetch_db1_with_keyword_logic(db_path, table, limit, preferred_title_col="xml_title"):
    """Mimic selection logic from VideoCreation2.py for db1 schema.
    Returns list of (id, blob, title) up to `limit`.
    Uses the actual DB schema discovered at runtime so it can work with slightly different tables/columns.
    """
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        table = resolve_table_name(conn, table, ["photos_2023_photos", "photos", "archived_files", "photos_searched"])
        ensure_airdate_column(conn, table)
        table, blob_col, title_col = resolve_table_columns(conn, table, preferred_title_col=preferred_title_col)
        if not table or not blob_col:
            conn.close()
            print(f"No usable image blob column found for table {table or '?'} in {db_path}")
            return []
        print(f"DB1 using table '{table}' with blob column '{blob_col}' and title column '{title_col or 'none'}'")
        try:
            idx_name = f"idx_{table}_VideoAirDate"
            cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}(VideoAirDate)")
            conn.commit()
        except Exception:
            pass
    except Exception:
        conn.close()
        return []

    # keyword list from original script
    keywords = [
        'actress', 'actor', 'singer', 'Monroe', 'Rita', 'pin up', 'Sandra', 'Brigitte', 'Emma', 'Jessica',
        'Jennifer', 'Dorothy', 'Kim', 'Elizabeth', 'Famke', 'Natalie', 'Sigourney', 'Eva', 'Marianne',
        'Helen', 'Lavinia', 'Jeanne', 'Nikki', 'Rose', 'Anita', 'Adrienne', 'Samantha', 'Adele', 'Ann',
        'Ava', 'Audrey', 'Michele', 'Claudia', 'Ursula', 'Jersey', 'New York', 'Washington', 'Detroit',
        'Chicago', 'Ohio', 'Oklahoma', 'Florida', 'Michigan', 'Bette', 'Barbara', 'Rochelle', 'Virginia'
    ]

    low_keywords = [k.lower() for k in keywords]

    candidate_rows = []
    pool_limit = min(max(limit * 20, 200), 2000)

    title_expr = title_col if title_col else "NULL"
    title_filter = f" AND ({title_col} IS NULL OR {title_col} NOT IN ('intro','outro'))" if title_col else ""

    try:
        cur.execute(f"SELECT id, {title_expr} FROM {table} WHERE (VideoAirDate IS NULL OR VideoAirDate = ''){title_filter} ORDER BY id DESC LIMIT ?", (pool_limit,))
        candidate_rows.extend(cur.fetchall())
    except Exception:
        pass

    if len(candidate_rows) < limit * 3:
        try:
            rem = max(limit * 2, pool_limit - len(candidate_rows))
            cur.execute(f"SELECT id, {title_expr} FROM {table} WHERE (VideoAirDate IS NOT NULL AND VideoAirDate != ''){title_filter} ORDER BY VideoAirDate ASC, id DESC LIMIT ?", (rem,))
            candidate_rows.extend(cur.fetchall())
        except Exception:
            pass

    keyword_rows = []
    non_keyword_rows = []
    for rid, title in candidate_rows:
        t = (title or "").lower()
        if any(kw in t for kw in low_keywords):
            keyword_rows.append((rid, title))
        else:
            non_keyword_rows.append((rid, title))

    conn.close()
    combined = intersperse_images(keyword_rows, non_keyword_rows, max_images=limit)
    ids = [r[0] for r in combined]
    if not ids:
        return []

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        placeholders = ','.join(['?'] * len(ids))
        cur.execute(f"SELECT id, {blob_col}, {title_expr} FROM {table} WHERE id IN ({placeholders})", ids)
        rows = cur.fetchall()
    except Exception:
        rows = []
    conn.close()

    blob_map = {r[0]: (r[1], r[2] if len(r) > 2 else '') for r in rows}
    out = []
    for iid in ids:
        if iid in blob_map:
            blob, title = blob_map[iid]
            out.append((iid, blob, title or ""))
    return out


def fetch_db2_prioritize(db_path, table, limit, preferred_title_col="description"):
    """Mimic selection logic from VideoFromPhotosTable.py for db2: prefer VideoAirDate NULL first.
    Fast queries: split into two indexed lookups.
    """
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        table = resolve_table_name(conn, table, ["image_comp", "images"])
        ensure_airdate_column(conn, table)
        table, blob_col, title_col = resolve_table_columns(conn, table, preferred_title_col=preferred_title_col)
        if not table or not blob_col:
            conn.close()
            print(f"No usable image blob column found for table {table or '?'} in {db_path}")
            return []
        print(f"DB2 using table '{table}' with blob column '{blob_col}' and title column '{title_col or 'none'}'")
        try:
            idx_name = f"idx_{table}_VideoAirDate"
            cur.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}(VideoAirDate)")
            conn.commit()
        except Exception:
            pass
    except Exception:
        conn.close()
        return []

    rows_meta = []
    title_expr = title_col if title_col else "NULL"

    try:
        cur.execute(f"SELECT id, {title_expr} FROM {table} WHERE (VideoAirDate IS NULL OR VideoAirDate = '') ORDER BY id DESC LIMIT ?", (limit * 3,))
        rows_meta.extend(cur.fetchall())
    except Exception:
        pass

    if len(rows_meta) < limit * 2:
        try:
            rem = max(limit * 2, (limit * 3) - len(rows_meta))
            cur.execute(f"SELECT id, {title_expr} FROM {table} WHERE (VideoAirDate IS NOT NULL AND VideoAirDate != '') ORDER BY VideoAirDate ASC, id DESC LIMIT ?", (rem,))
            rows_meta.extend(cur.fetchall())
        except Exception:
            pass

    conn.close()

    ids = [r[0] for r in rows_meta]
    if not ids:
        return []

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        placeholders = ','.join(['?'] * len(ids))
        cur.execute(f"SELECT id, {blob_col}, {title_expr} FROM {table} WHERE id IN ({placeholders})", ids)
        rows = cur.fetchall()
    except Exception:
        rows = []
    conn.close()

    blob_map = {r[0]: (r[1], r[2] if len(r) > 2 else '') for r in rows}
    out = []
    for iid in ids:
        if iid in blob_map:
            blob, title = blob_map[iid]
            out.append((iid, blob, title or ""))
    return out


def star_bg():
    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    d = ImageDraw.Draw(img)
    for _ in range(200):
        x, y = random.randint(0, WIDTH), random.randint(0, HEIGHT)
        r = random.randint(1, 2)
        d.ellipse((x - r, y - r, x + r, y + r), fill="white")
    return img


# Pre-generate a small cache of star backgrounds to avoid expensive per-image drawing.
_STAR_BG_CACHE = None

def init_star_backgrounds(n=6):
    global _STAR_BG_CACHE
    if _STAR_BG_CACHE is not None:
        return
    cache = []
    for i in range(n):
        # Slightly vary seed to get different patterns
        random.seed(i + 12345)
        cache.append(star_bg())
    _STAR_BG_CACHE = cache


def render_photo_pil(blob, text):
    """Render a photo and return a PIL Image (RGB)."""
    # Use pre-generated background to avoid drawing stars per image
    try:
        init_star_backgrounds()
        bg = _STAR_BG_CACHE[random.randint(0, len(_STAR_BG_CACHE) - 1)].copy()
    except Exception:
        bg = star_bg()
    try:
        img = Image.open(io.BytesIO(blob)).convert("RGB")
    except Exception:
        return None

    # Enlarge small images similar to VideoCreation2.py logic
    min_width_threshold = WIDTH * 0.6
    min_height_threshold = HEIGHT * 0.6
    img_width, img_height = img.size

    scale_factor = 1.0
    if img_width < min_width_threshold or img_height < min_height_threshold:
        scale_factor = max(
            min_width_threshold / img_width,
            min_height_threshold / img_height,
            1.5
        )
        scale_factor = min(scale_factor, 4.0)

    if scale_factor != 1.0:
        new_width = int(img_width * scale_factor)
        new_height = int(img_height * scale_factor)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    img.thumbnail((int(WIDTH * 0.9), int(HEIGHT * 0.9)), Image.Resampling.LANCZOS)
    bg.paste(img, ((WIDTH - img.width) // 2, (HEIGHT - img.height) // 2))

    if text:
        try:
            global _COMMON_FONT
            try:
                font = _COMMON_FONT
            except NameError:
                try:
                    _COMMON_FONT = ImageFont.truetype("arial.ttf", 42)
                except Exception:
                    _COMMON_FONT = ImageFont.load_default()
                font = _COMMON_FONT
        except Exception:
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

    return bg


def render_photo(blob, text):
    pil = render_photo_pil(blob, text)
    if pil is None:
        return None
    return np.array(pil)


def update_video_airdate(db_path, table, rows):
    """Update VideoAirDate.
    Accepts either:
      - rows = [(id,)] or [id, id, ...] -> will set same current timestamp for each id
      - rows = [(id, stamp_str), ...] or [(stamp_str, id), ...] depending on caller
    Prefer callers to pass (id, stamp_str) pairs.
    """
    if not rows:
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        first = rows[0]
        # If first element is a tuple of length 2 and first item is int -> assume (id, stamp)
        if isinstance(first, (list, tuple)) and len(first) == 2:
            # Normalize to (stamp, id) for executemany
            exec_rows = []
            for a, b in rows:
                # try both orders: (id, stamp) or (stamp, id)
                if isinstance(a, int) or (isinstance(a, str) and a.isdigit()):
                    exec_rows.append((b, a))
                else:
                    exec_rows.append((a, b))
            cur.executemany(f"UPDATE {table} SET VideoAirDate = ? WHERE id = ?", exec_rows)
        else:
            # assume list of ids - set same timestamp for all in a single executemany
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.executemany(f"UPDATE {table} SET VideoAirDate = ? WHERE id = ?", [(stamp, i) for i in rows])
        conn.commit()
    finally:
        conn.close()


def ffmpeg_bin():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    win = r"C:\ffmpeg-8.0.1-essentials_build\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"
    if os.path.isfile(win):
        return win
    raise RuntimeError("ffmpeg not found")


def interleave_lists(a, b):
    """Interleave two lists trying to keep them evenly distributed."""
    out = []
    la, lb = len(a), len(b)
    if la == 0:
        return b.copy()
    if lb == 0:
        return a.copy()
    # Determine step for larger/smaller
    if la >= lb:
        step = max(1, la // (lb + 1))
        ai = 0
        bi = 0
        while ai < la or bi < lb:
            for _ in range(step):
                if ai < la:
                    out.append(a[ai])
                    ai += 1
            if bi < lb:
                out.append(b[bi])
                bi += 1
        return out
    else:
        return interleave_lists(b, a)


def main():
    global BASE
    p = argparse.ArgumentParser(description="Combine images from two DBs into a slideshow with a percentage split.")
    p.add_argument("--db1", required=True, help="Path to DB used by VideoCreation2 (e.g. universal_image_archive.db)")
    p.add_argument("--db1-table", default=DEFAULT_DB1_TABLE)
    p.add_argument("--db1-title-col", default="xml_title", help="Title column name in db1 (or blank)")
    p.add_argument("--db2", required=True, help="Path to DB used by VideoFromPhotosTable (e.g. image_collection.db)")
    p.add_argument("--db2-table", default=DEFAULT_DB2_TABLE)
    p.add_argument("--db2-title-col", default="description", help="Title/description column name in db2 (or blank)")
    p.add_argument("--total", type=int, default=35, help="Total number of images to include")
    p.add_argument("--pct1", type=int, default=50, help="Percentage of images from db1 (0-100). db2 will be 100-pct1")
    p.add_argument("--n1", type=int, default=None, help="Exact number of images to take from db1 (overrides pct/total)")
    p.add_argument("--n2", type=int, default=None, help="Exact number of images to take from db2 (overrides pct/total)")
    p.add_argument("--outdir", required=True, help="Output directory for video and temp files")
    p.add_argument("--skip-audio", action="store_true", help="Skip audio muxing for faster builds (for testing/quick preview)")
    p.add_argument("--air-date", default=None, help="Scheduled air date of the video (YYYY-MM-DD HH:MM:SS)")
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # record overall run start for runtime logging
    run_start_time = datetime.now()

    pct1 = max(0, min(100, args.pct1))
    # allow explicit per-db counts to override percentage/total
    if args.n1 is not None or args.n2 is not None:
        n1 = args.n1 if args.n1 is not None else 0
        n2 = args.n2 if args.n2 is not None else 0
        # if only one provided, try to fill to total
        if args.n1 is not None and args.n2 is None:
            n2 = max(0, args.total - n1)
        if args.n2 is not None and args.n1 is None:
            n1 = max(0, args.total - n2)
    else:
        n1 = round(args.total * (pct1 / 100.0))
        n2 = args.total - n1

    def resolve_db_path(path, fallback_candidates):
        def is_valid_db(candidate):
            if not candidate or not os.path.exists(candidate):
                return False
            try:
                conn = sqlite3.connect(candidate)
                try:
                    conn.execute("SELECT name FROM sqlite_master LIMIT 1")
                    return True
                finally:
                    conn.close()
            except Exception:
                return False

        if path and is_valid_db(path):
            return path
        for candidate in fallback_candidates:
            if is_valid_db(candidate):
                return candidate
        return path

    db1_path = resolve_db_path(args.db1, [os.path.join(BASE, "universal_image_archive.db"), os.path.join(BASE, "photos_2023_photos.db")])
    db2_path = resolve_db_path(args.db2, [os.path.join(BASE, "image_collection.db")])
    print(f"Resolved db1 path: {db1_path}")
    print(f"Resolved db2 path: {db2_path}")
    print(f"Selecting up to {n1} images from db1 and {n2} images from db2 (total {args.total})")

    # Use original scripts' selection logic (measure durations)
    t0 = time.perf_counter()
    rows1 = fetch_db1_with_keyword_logic(db1_path, args.db1_table, n1, preferred_title_col=args.db1_title_col.strip() or "xml_title")
    t1 = time.perf_counter()
    print(f"DB1 selection took {t1 - t0:.2f}s and returned {len(rows1)} rows")

    t0 = time.perf_counter()
    rows2 = fetch_db2_prioritize(db2_path, args.db2_table, n2, preferred_title_col=args.db2_title_col.strip() or "description")
    t1 = time.perf_counter()
    print(f"DB2 selection took {t1 - t0:.2f}s and returned {len(rows2)} rows")

    print(f"Available: db1={len(rows1)} rows, db2={len(rows2)} rows")

    # Adjust if not enough available
    if len(rows1) < n1:
        short = n1 - len(rows1)
        n2 = min(args.total - len(rows1), len(rows2))
        print(f"db1 short by {short}. Adjusting db2 quota to {n2}.")
    if len(rows2) < n2:
        short = n2 - len(rows2)
        n1 = min(args.total - len(rows2), len(rows1))
        print(f"db2 short by {short}. Adjusting db1 quota to {n1}.")

    # Trim to quotas
    rows1 = rows1[:n1]
    rows2 = rows2[:n2]

    # Optionally shuffle within each source for variety
    random.shuffle(rows1)
    random.shuffle(rows2)

    # Interleave to keep distribution
    combined = interleave_lists(rows1, rows2)
    if len(combined) > args.total:
        combined = combined[: args.total]

    print(f"Final combined list length: {len(combined)}")
    if not combined:
        print("No images selected from either database. Check the database paths, table names and schema.")
        return

    # We'll stream frames to disk to avoid huge in-memory lists
    used1 = []  # will hold tuples (id, timestamp_str)
    used2 = []

    # Determine base start_time for VideoAirDate stamps
    start_time_base = None
    if args.air_date:
        try:
            start_time_base = datetime.strptime(args.air_date, "%Y-%m-%d %H:%M:%S")
            print(f"Using explicitly provided air date: {start_time_base}")
        except Exception as e:
            print(f"Warning: Failed to parse provided air-date '{args.air_date}': {e}")

    if not start_time_base and args.outdir:
        # Try to parse the scheduled date from the outdir path (e.g. YYYYMMdd-HHh)
        import re
        basename = os.path.basename(os.path.abspath(args.outdir))
        match = re.search(r"(\d{8})-(\d{2})h", basename)
        if match:
            try:
                date_part, hour_part = match.groups()
                start_time_base = datetime.strptime(f"{date_part} {hour_part}", "%Y%m%d %H")
                print(f"Automatically parsed air date from outdir '{basename}': {start_time_base}")
            except Exception as e:
                print(f"Warning: Failed to parse date from outdir '{basename}': {e}")
        else:
            # Try a broader search in the full outdir path for any YYYYMMdd-HHh
            match_full = re.search(r"(\d{8})-(\d{2})h", args.outdir)
            if match_full:
                try:
                    date_part, hour_part = match_full.groups()
                    start_time_base = datetime.strptime(f"{date_part} {hour_part}", "%Y%m%d %H")
                    print(f"Automatically parsed air date from full outdir path: {start_time_base}")
                except Exception as e:
                    pass

    if not start_time_base:
        start_time_base = datetime.now()
        print(f"Using execution time for air date: {start_time_base}")

    # compute start_time base for VideoAirDate stamps (include intro duration if intro image exists)
    BASE = os.path.dirname(os.path.abspath(__file__))
    ASSETS = os.path.join(BASE, "VideoAssets")
    INTRO_IMAGE = os.path.join(ASSETS, "Logo.jpg")
    intro_offset = INTRO_DURATION if os.path.exists(INTRO_IMAGE) else 0
    from datetime import timedelta
    start_time = start_time_base + timedelta(seconds=intro_offset)

    # Make quick lookup sets for source detection (O(1) membership checks)
    ids1_set = set(r[0] for r in rows1)
    ids2_set = set(r[0] for r in rows2)

    # Prepare paths and temp folders for ffmpeg-based slideshow creation
    out_video = os.path.join(args.outdir, "combined_slideshow.mp4")
    total_frames_written = 0

    # Intro: prepare intro image/video if present
    intro_frames = None
    num_frames_intro = int(INTRO_DURATION * FPS)
    INTRO_IMAGE = os.path.join(ASSETS, "Logo.jpg")
    intro_mp4 = None
    if os.path.exists(INTRO_IMAGE):
        try:
            with open(INTRO_IMAGE, 'rb') as f:
                intro_frames = process_intro_outro_image(io.BytesIO(f.read()), WIDTH, HEIGHT, num_frames_intro, FPS, is_intro=True)
            if intro_frames:
                # save a single intro image and make a short intro mp4 with ffmpeg (looped)
                tmp_dir = os.path.join(args.outdir, '_tmp_intro')
                shutil.rmtree(tmp_dir, ignore_errors=True)
                os.makedirs(tmp_dir, exist_ok=True)
                intro_jpg = os.path.join(tmp_dir, 'intro.jpg')
                Image.fromarray(intro_frames[0]).save(intro_jpg, format='JPEG', quality=90)
                intro_mp4 = os.path.join(args.outdir, '_intro.mp4')
                # use faster preset for quicker encoding during slideshow builds
                cmd_intro = [ffmpeg_bin(), '-y', '-loop', '1', '-i', intro_jpg, '-t', str(INTRO_DURATION), '-s', f"{WIDTH}x{HEIGHT}", '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-r', str(FPS), intro_mp4]
                try:
                    subprocess.run(cmd_intro, check=True)
                    print(f"Prepared intro video: {intro_mp4}")
                except Exception as e:
                    print(f"Failed to create intro video: {e}")
                    intro_mp4 = None
        except Exception as e:
            print(f"Failed to process intro image: {e}")
    else:
        print(f"Intro image not found at {INTRO_IMAGE}. Continuing without intro.")

    # Render slideshow images to a temp folder (ffmpeg will build the video)
    tmp_img_dir = os.path.join(args.outdir, "_tmp_images")
    shutil.rmtree(tmp_img_dir, ignore_errors=True)
    os.makedirs(tmp_img_dir, exist_ok=True)

    def _save_image_task(args_tuple):
        i, pid, blob, title = args_tuple
        pil = render_photo_pil(blob, title)
        if pil is None:
            return (i, pid, False)
        path = os.path.join(tmp_img_dir, f"img{i:05d}.jpg")
        pil.save(path, format='JPEG', quality=85)
        return (i, pid, True)

    tasks = [(i + 1, pid, blob, title) for i, (pid, blob, title) in enumerate(combined)]
    # Use ThreadPoolExecutor (PIL operations release GIL, giving good parallelism)
    max_workers = min(8, (os.cpu_count() or 4))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exc:
        futures = [exc.submit(_save_image_task, t) for t in tasks]
        for fut in concurrent.futures.as_completed(futures):
            i, pid, ok = fut.result()
            if not ok:
                print(f"Skipping id {pid} (failed to render)")
            else:
                total_frames_written += 1
                offset_seconds = (i - 1) * IMAGE_SEC
                stamp = (start_time + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%d %H:%M:%S")
                if pid in ids1_set:
                    used1.append((pid, stamp))
                elif pid in ids2_set:
                    used2.append((pid, stamp))

    # Build slideshow video via ffmpeg from the saved images (each image shown for IMAGE_SEC seconds)
    slideshow_mp4 = os.path.join(args.outdir, "_slideshow.mp4")
    fr_str = f"1/{int(IMAGE_SEC)}"
    # use faster encoding preset and slightly higher CRF for much faster runs
    cmd = [ffmpeg_bin(), '-y', '-framerate', fr_str, '-i', os.path.join(tmp_img_dir, 'img%05d.jpg'), '-s', f"{WIDTH}x{HEIGHT}", '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '23', '-r', str(FPS), slideshow_mp4]
    try:
        subprocess.run(cmd, check=True)
        print(f"Slideshow video created: {slideshow_mp4}")
    except Exception as e:
        print(f"Failed to create slideshow video via ffmpeg: {e}")

    # Create outro video if available, then concat intro + slideshow + outro into final video
    ASSETS = os.path.join(BASE, "VideoAssets")
    outro_mp4 = None
    outro_exists = False
    OUTRO_IMAGE = os.path.join(ASSETS, "End Screen V2.png")
    if os.path.exists(OUTRO_IMAGE):
        try:
            num_frames_outro = int(OUTRO_DURATION * FPS)
            outro_frames = process_intro_outro_image(open(OUTRO_IMAGE, 'rb'), WIDTH, HEIGHT, num_frames_outro, FPS, is_intro=False)
            if outro_frames:
                tmp_out_dir = os.path.join(args.outdir, '_tmp_outro')
                shutil.rmtree(tmp_out_dir, ignore_errors=True)
                os.makedirs(tmp_out_dir, exist_ok=True)
                for i, fr in enumerate(outro_frames, start=1):
                    Image.fromarray(fr).save(os.path.join(tmp_out_dir, f"out{i:05d}.png"), format='PNG')
                outro_mp4 = os.path.join(args.outdir, '_outro.mp4')
                cmd_out = [ffmpeg_bin(), '-y', '-framerate', str(FPS), '-i', os.path.join(tmp_out_dir, 'out%05d.png'), '-s', f"{WIDTH}x{HEIGHT}", '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '23', '-r', str(FPS), outro_mp4]
                try:
                    subprocess.run(cmd_out, check=True)
                    outro_exists = True
                    print(f"Prepared outro video: {outro_mp4}")
                except Exception as e:
                    print(f"Failed to create outro video: {e}")
                    outro_exists = False
        except Exception as e:
            print(f"Failed to process outro image: {e}")
    else:
        print(f"Outro image not found at {OUTRO_IMAGE}. Continuing without outro.")

    # Build final concatenated video (re-encode to ensure compatibility)
    parts = []
    if intro_mp4 and os.path.exists(intro_mp4):
        parts.append(intro_mp4)
    if os.path.exists(slideshow_mp4):
        parts.append(slideshow_mp4)
    if outro_exists and outro_mp4 and os.path.exists(outro_mp4):
        parts.append(outro_mp4)

    if not parts:
        print("No video parts created; aborting final assembly.")
    else:
        concat_txt = os.path.join(args.outdir, 'concat_list.txt')
        with open(concat_txt, 'w', encoding='utf-8') as cf:
            for pth in parts:
                abs_p = os.path.abspath(pth).replace('\\', '/')
                print(f"Concat entry: {abs_p} exists:{os.path.exists(pth)}")
                cf.write(f"file '{abs_p}'\n")
        try:
            # re-encode to final output to be safe
            # faster preset for concatenation/re-encode step
            cmd_cat = [ffmpeg_bin(), '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '23', '-r', str(FPS), out_video]
            subprocess.run(cmd_cat, check=True)
            print(f"Final video assembled: {out_video}")
        except Exception as e:
            print(f"Failed to concat video parts: {e}")
    # record runtime and append to SanityChecks/RunTimeChecks.txt
    try:
        run_end_time = datetime.now()
        elapsed = run_end_time - run_start_time
        elapsed_s = int(elapsed.total_seconds())
        # human friendly H:MM:SS
        h = elapsed_s // 3600
        m = (elapsed_s % 3600) // 60
        s = elapsed_s % 60
        elapsed_str = f"{h}:{m:02d}:{s:02d}"
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SanityChecks")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "RunTimeChecks.txt")
        with open(log_file, 'a', encoding='utf-8') as lf:
            lf.write(f"{run_end_time.strftime('%Y-%m-%d %H:%M:%S')} - {elapsed_str}\n")
        print(f"Run time: {elapsed_str} (logged to {log_file})")
    except Exception as e:
        print(f"Failed to write runtime log: {e}")

    # Add music using the selected background track plus the existing outro audio.
    images_count = len(used1) + len(used2)
    intro_duration = INTRO_DURATION if intro_frames else 0
    slideshow_duration = images_count * IMAGE_SEC
    outro_duration = OUTRO_DURATION if outro_frames else 0
    total_duration = intro_duration + slideshow_duration + outro_duration
    non_outro_duration = intro_duration + slideshow_duration
    
    if images_count > 0 and not args.skip_audio:
        try:
            AUDIO_FILE1 = os.path.join(ASSETS, "Gymnopedie no1 - Satie.mp3")
            AUDIO_FILE2 = os.path.join(ASSETS, "Dancing in the rain-piano ver. by Music Goreng.mp3")
            OUTRO_AUDIO = os.path.join(ASSETS, "Outro - The Time Then.mp4")

            if not (os.path.exists(AUDIO_FILE1) and os.path.exists(AUDIO_FILE2)):
                raise FileNotFoundError("One or both background audio files missing in VideoAssets; skipping audio mux.")

            # Split the non-outro duration evenly between the two tracks.
            audio1_duration = non_outro_duration / 2.0
            audio2_duration = non_outro_duration / 2.0

            audio1 = ffmpeg.input(AUDIO_FILE1).audio.filter('aloop', loop=-1, size='2e9').filter('atrim', start=0, end=audio1_duration)
            audio2 = ffmpeg.input(AUDIO_FILE2).audio.filter('aloop', loop=-1, size='2e9').filter('atrim', start=0, end=audio2_duration)

            if outro_duration > 0 and os.path.exists(OUTRO_AUDIO):
                outro_audio = ffmpeg.input(OUTRO_AUDIO).audio.filter('atrim', start=0, end=outro_duration).filter('aformat', sample_fmts='fltp', sample_rates=44100)
                combined_audio = ffmpeg.filter([audio1, audio2, outro_audio], 'concat', n=3, v=0, a=1)
            else:
                combined_audio = ffmpeg.filter([audio1, audio2], 'concat', n=2, v=0, a=1)

            video_stream = ffmpeg.input(out_video).video
            output_stream = ffmpeg.output(
                video_stream,
                combined_audio,
                out_video.replace('.mp4', '_with_audio.mp4'),
                vcodec='copy',
                acodec='aac',
                **{'b:a': '192k'},
                **{'t': total_duration},
                shortest=None
            )

            ffmpeg.run(output_stream, overwrite_output=True, quiet=False)
            final_video = out_video.replace('.mp4', '_with_audio.mp4')

            # Replace original with audio version
            if os.path.exists(final_video):
                os.remove(out_video)
                os.rename(final_video, out_video)

            print(f"Audio mux complete: {out_video}")

        except Exception as e:
            print(f"Audio processing skipped or failed: {e}")
    elif args.skip_audio:
        print("Audio muxing skipped (--skip-audio flag set)")

    # Always update VideoAirDate for used rows in their respective DBs.
    if used1:
        try:
            update_video_airdate(args.db1, args.db1_table, used1)
            print(f"Marked {len(used1)} rows in db1 with VideoAirDate.")
        except Exception as e:
            print(f"Failed to mark db1: {e}")
    if used2:
        try:
            update_video_airdate(args.db2, args.db2_table, used2)
            print(f"Marked {len(used2)} rows in db2 with VideoAirDate.")
        except Exception as e:
            print(f"Failed to mark db2: {e}")

    # Extract sample images from slideshow-only video so intro/outro are never sampled.
    # Fallback to final video only if slideshow part is unexpectedly missing.
    sample_source_video = slideshow_mp4 if os.path.exists(slideshow_mp4) else out_video
    print(f"Extracting sample images from: {sample_source_video}")
    samples_dir = os.path.join(args.outdir, "selected_images")
    if os.path.isdir(samples_dir):
        for name in os.listdir(samples_dir):
            if name.startswith("sample_") and name.lower().endswith(".jpg"):
                try:
                    os.remove(os.path.join(samples_dir, name))
                except Exception as e:
                    print(f"Failed to remove stale sample image {name}: {e}")
    else:
        os.makedirs(samples_dir, exist_ok=True)
    
    # Extract one frame every 5 seconds from the selected source video.
    try:
        # Use ffmpeg to extract frames at 0.2 fps (every 5 seconds)
        cmd_extract = [ffmpeg_bin(), '-i', sample_source_video, '-vf', 'fps=0.2', os.path.join(samples_dir, 'sample_%02d.jpg')]
        subprocess.run(cmd_extract, check=True, capture_output=True)
        sample_count = len([f for f in os.listdir(samples_dir) if f.startswith('sample_') and f.endswith('.jpg')])
        print(f"Extracted {sample_count} sample images from source video")
    except Exception as e:
        print(f"Failed to extract sample images from source video: {e}")

    # Clean up temporary files and directories
    print("Cleaning up temporary files...")
    temp_dirs = ['_tmp_intro', '_tmp_images', '_tmp_outro']
    temp_files = ['concat_list.txt', '_intro.mp4', '_slideshow.mp4', '_outro.mp4']
    
    for td in temp_dirs:
        tmp_path = os.path.join(args.outdir, td)
        if os.path.isdir(tmp_path):
            try:
                shutil.rmtree(tmp_path)
                print(f"Removed temp dir: {td}")
            except Exception as e:
                print(f"Failed to remove {td}: {e}")
    
    for tf in temp_files:
        tmp_path = os.path.join(args.outdir, tf)
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
                print(f"Removed temp file: {tf}")
            except Exception as e:
                print(f"Failed to remove {tf}: {e}")

    print(f"Done. Final video: {out_video}")


if __name__ == '__main__':
    main()
