import subprocess
import pytesseract
import cv2
import os
import sys
import re
import sqlite3
import hashlib
from collections import Counter
import json
import math
import shutil  # for which()
import numpy as np

# Optional post-processing: rewrite extracted text using rewrite_extracted_text.py
try:
    import rewrite_extracted_text as _rewrite_mod
except Exception:
    _rewrite_mod = None

# ================= CONFIG =================
# Prefer detecting executables via PATH if possible (more portable)
FFMPEG_PATH = shutil.which("ffmpeg") or r"C:\ffmpeg\ffmpeg-8.0.1-essentials_build\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"
FFPROBE_PATH = shutil.which("ffprobe") or r"C:\ffmpeg\ffmpeg-8.0.1-essentials_build\ffmpeg-8.0.1-essentials_build\bin\ffprobe.exe"
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

TEXT_START_SEC = 3
STEP_SEC = 12
IMAGE_OFFSET = 9   # image = text + 9s

OUTPUT_DIR = "output"
TEXT_FILE = "extracted_text.txt"
EXTRA_DUPLICATE_DIRS = ("output-ready", "Output")

TEMP_TEXT_FRAME = "_frame_text.jpg"
TEMP_IMAGE_FRAME = "_frame_image.jpg"

MAX_SUMMARY_WORDS = 4
DB_NAME = "image_collection.db"
DB_TABLE_NAME = "image_comp"
VISUAL_DUPLICATE_DISTANCE_THRESHOLD = 6
# =========================================

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
os.makedirs(OUTPUT_DIR, exist_ok=True)

STOPWORDS = {
    "the","a","an","of","in","on","and","or","to","with",
    "photo","image","picture","signed","by","from",
    "was","were","is","are","this","that","last","stretch"
}

# ================= VIDEO DURATION =================

def get_video_duration(video_path):
    """
    Get video duration in seconds (float) using ffprobe - Option 1 style
    """
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True
        )
        duration_str = result.stdout.strip()
        if not duration_str:
            raise ValueError("ffprobe returned empty duration")
        return float(duration_str)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed (code {e.returncode}):\n{e.stderr.strip()}")
    except FileNotFoundError:
        raise RuntimeError(f"ffprobe not found at: {FFPROBE_PATH}\nMake sure it's installed and in PATH.")
    except ValueError as e:
        raise RuntimeError(f"Could not parse duration: {e}")

# ================= FRAME EXTRACTION =================

def extract_frame(video, second, out_file):
    cmd = [
        FFMPEG_PATH, "-y",
        "-ss", str(second),
        "-i", video,
        "-frames:v", "1",
        "-q:v", "2",
        out_file
    ]
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Warning: frame extraction failed at {second}s → {e}")
        return False
    except FileNotFoundError:
        print(f"Error: ffmpeg not found at {FFMPEG_PATH}")
        return False
    return True

# ================= OCR =================

def crop_caption_region(img):
    h, w = img.shape[:2]
    y_start = int(h * 0.65)
    return img[y_start:h, 0:w]

def ocr_image(img):
    caption = crop_caption_region(img)

    gray = cv2.cvtColor(caption, cv2.COLOR_BGR2GRAY)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    raw = pytesseract.image_to_string(
        gray,
        config="--oem 3 --psm 6"
    )

    return clean_ocr_text(raw)

# ================= TEXT CLEANING =================

def clean_ocr_text(text):
    text = text.replace("\n", " ").strip()
    text = re.sub(r"^[^A-Za-z]{1,20}", "", text)
    text = re.sub(r"^\d+\s*", "", text)

    fixes = {
        r"\bata\b": "at a",
        r"\binthe\b": "in the",
        r"\btrainin g\b": "training",
    }

    for p, r in fixes.items():
        text = re.sub(p, r, text, flags=re.IGNORECASE)

    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ================= SUMMARY =================

def summarize_text(text, max_words=4):
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return "image"

    lower = [w.lower() for w in words]

    years = [w for w in lower if re.fullmatch(r"(18|19|20)\d{2}", w)]
    proper = [w.lower() for w in words if w[0].isupper() and w.lower() not in STOPWORDS]
    keywords = [w for w in lower if w not in STOPWORDS and len(w) > 3]

    scored = Counter()
    for w in years: scored[w] += 5
    for w in proper: scored[w] += 4
    for w in keywords: scored[w] += 1

    summary = [w for w, _ in scored.most_common(max_words)]
    return "_".join(summary) if summary else "image"

# ================= INDEX =================

def get_next_index(text_path):
    if not os.path.exists(text_path):
        return 1

    max_idx = 0
    with open(text_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*(\d+)\s*\|", line)
            if m:
                max_idx = max(max_idx, int(m.group(1)))
    return max_idx + 1

# ================= DUPLICATE CHECK =================

def compute_dhash_from_image(img, hash_size=8):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = "".join("1" if v else "0" for v in diff.flatten())
    return format(int(bits, 2), "016x")


def compute_sha256_from_image(img):
    ok, encoded = cv2.imencode(".png", img)
    if not ok:
        return ""
    return hashlib.sha256(encoded.tobytes()).hexdigest()


def compute_pixel_sha256_from_image(img):
    """Compute pixel SHA256 using PIL-compatible format for consistency with insert_photos script."""
    if img is None or img.size == 0:
        return ""
    # Convert BGR to RGB to match PIL's RGB format
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]
    # Use PIL-compatible shape format: "WxH" (width x height)
    shape_bytes = f"{w}x{h}".encode("utf-8")
    return hashlib.sha256(img_rgb.tobytes() + shape_bytes).hexdigest()


def compute_ahash_from_image(img, hash_size=8):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    avg = resized.mean()
    diff = resized >= avg
    bits = "".join("1" if v else "0" for v in diff.flatten())
    return format(int(bits, 2), "016x")


def hamming_distance(hash_a, hash_b):
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def compute_hash_variants(img):
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return None

    full = img
    top_crop = img[: max(1, int(h * 0.82)), :]

    y1 = int(h * 0.08)
    y2 = int(h * 0.92)
    x1 = int(w * 0.08)
    x2 = int(w * 0.92)
    center_crop = img[y1:y2, x1:x2]

    dhash_variants = []
    ahash_variants = []
    for part in (full, top_crop, center_crop):
        if part is None or part.size == 0:
            continue
        dhash_variants.append(compute_dhash_from_image(part))
        ahash_variants.append(compute_ahash_from_image(part))

    return {
        "sha256": compute_sha256_from_image(full),
        "pixel_sha256": compute_pixel_sha256_from_image(full),
        "dhashes": dhash_variants,
        "ahashes": ahash_variants,
    }


def decode_blob_to_image(file_data):
    np_data = np.frombuffer(file_data, dtype=np.uint8)
    return cv2.imdecode(np_data, cv2.IMREAD_COLOR)


def build_duplicate_index_from_db():
    if not os.path.exists(DB_NAME):
        print(f"⚠️ Duplicate check DB not found: {DB_NAME}. Continuing with output-folder checks only.")
        return []

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (DB_TABLE_NAME,))
    if cursor.fetchone() is None:
        conn.close()
        print(f"⚠️ Duplicate check table not found: {DB_TABLE_NAME}. Continuing with output-folder checks only.")
        return []

    cursor.execute(f"SELECT id, filename, file_data FROM {DB_TABLE_NAME}")
    rows = cursor.fetchall()
    conn.close()

    index = []
    for row_id, filename, file_data in rows:
        if not file_data:
            continue
        img = decode_blob_to_image(file_data)
        if img is None:
            continue
        hashes = compute_hash_variants(img)
        if hashes is None:
            continue
        index.append(
            {
                "source": "db",
                "id": row_id,
                "name": filename or f"id_{row_id}",
                "sha256": hashes["sha256"],
                "pixel_sha256": hashes["pixel_sha256"],
                "dhashes": hashes["dhashes"],
                "ahashes": hashes["ahashes"],
            }
        )
    return index


def build_duplicate_index_from_dir(directory):
    index = []
    if not os.path.isdir(directory):
        return index

    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        if not re.search(r"\.(png|jpg|jpeg|webp|bmp|tif|tiff)$", name, re.IGNORECASE):
            continue
        img = cv2.imread(path)
        if img is None:
            continue
        hashes = compute_hash_variants(img)
        if hashes is None:
            continue
        index.append(
            {
                "source": "output",
                "id": None,
                "name": name,
                "sha256": hashes["sha256"],
                "pixel_sha256": hashes["pixel_sha256"],
                "dhashes": hashes["dhashes"],
                "ahashes": hashes["ahashes"],
            }
        )
    return index


def build_duplicate_index_from_outputs():
    index = []
    seen_paths = set()

    for folder in (OUTPUT_DIR,) + EXTRA_DUPLICATE_DIRS:
        abs_path = os.path.abspath(folder)
        if abs_path in seen_paths:
            continue
        seen_paths.add(abs_path)
        index.extend(build_duplicate_index_from_dir(folder))

    return index


def check_visual_duplicate(img, duplicate_index):
    candidate = compute_hash_variants(img)
    if candidate is None:
        return None

    for entry in duplicate_index:
        # First check: exact pixel match (most reliable)
        if (
            candidate["pixel_sha256"]
            and entry["pixel_sha256"]
            and candidate["pixel_sha256"] == entry["pixel_sha256"]
        ):
            return {
                "type": "exact",
                "entry": entry,
                "distance": 0,
            }

        # Second check: SHA256 match (reliable for identical encodings)
        if candidate["sha256"] and entry["sha256"] and candidate["sha256"] == entry["sha256"]:
            return {
                "type": "exact",
                "entry": entry,
                "distance": 0,
            }

        # Third check: visual similarity (dhashes and ahashes)
        # Check all candidate hashes against all entry hashes
        for candidate_dhash in candidate["dhashes"]:
            for entry_dhash in entry["dhashes"]:
                distance = hamming_distance(candidate_dhash, entry_dhash)
                if distance <= VISUAL_DUPLICATE_DISTANCE_THRESHOLD:
                    return {
                        "type": "visual",
                        "entry": entry,
                        "distance": distance,
                    }

        for candidate_ahash in candidate["ahashes"]:
            for entry_ahash in entry["ahashes"]:
                distance = hamming_distance(candidate_ahash, entry_ahash)
                if distance <= VISUAL_DUPLICATE_DISTANCE_THRESHOLD:
                    return {
                        "type": "visual",
                        "entry": entry,
                        "distance": distance,
                    }

    return None


def add_image_to_duplicate_index(img, name, duplicate_index):
    hashes = compute_hash_variants(img)
    if hashes is None:
        return
    duplicate_index.append(
        {
            "source": "output",
            "id": None,
            "name": name,
            "sha256": hashes["sha256"],
            "pixel_sha256": hashes["pixel_sha256"],
            "dhashes": hashes["dhashes"],
            "ahashes": hashes["ahashes"],
        }
    )

# ================= PROCESS =================

def process_entry(video, text_sec, img_sec, index, text_path, duplicate_index):
    # Extract text frame
    if not extract_frame(video, text_sec, TEMP_TEXT_FRAME):
        return False

    img_text = cv2.imread(TEMP_TEXT_FRAME)
    if img_text is None:
        print(f"Failed to read text frame at {text_sec}s")
        return False

    text = ocr_image(img_text)

    # Extract image frame
    if not extract_frame(video, img_sec, TEMP_IMAGE_FRAME):
        return False

    img = cv2.imread(TEMP_IMAGE_FRAME)
    if img is None:
        print(f"Failed to read image frame at {img_sec}s")
        return False

    duplicate_hit = check_visual_duplicate(img, duplicate_index)
    if duplicate_hit is not None:
        hit = duplicate_hit["entry"]
        if duplicate_hit["type"] == "exact":
            print(f"⏭️  #{index} skipped (exact duplicate) vs {hit['source']}:{hit['name']}")
        else:
            print(
                f"⏭️  #{index} skipped (visual duplicate, d={duplicate_hit['distance']}) "
                f"vs {hit['source']}:{hit['name']}"
            )
        return False

    summary = summarize_text(text, MAX_SUMMARY_WORDS)
    filename = f"{summary}--{index}.png"
    output_path = os.path.join(OUTPUT_DIR, filename)

    # Append text only after duplicate check passes
    with open(text_path, "a", encoding="utf-8") as f:
        f.write(f"{index} | {text}\n")

    cv2.imwrite(output_path, img)
    add_image_to_duplicate_index(img, filename, duplicate_index)

    print(f"✅ #{index}  text={text_sec:.1f}s  image={img_sec:.1f}s  → {filename}")
    return True

# ================= MAIN =================

def main():
    if len(sys.argv) < 2:
        print("Usage: python auto_extract_historical_photos.py <video_path>")
        sys.exit(1)

    video = sys.argv[1]
    if not os.path.isfile(video):
        try:
            print(f"Error: Video file not found: {video}")
        except UnicodeEncodeError:
            print(f"Error: Video file not found (path contains special characters)")
        sys.exit(1)

    try:
        duration = get_video_duration(video)
        print(f"Video duration: {duration:.2f} seconds")
    except Exception as e:
        print(f"Error getting duration: {e}")
        sys.exit(1)

    text_path = os.path.join(OUTPUT_DIR, TEXT_FILE)
    index = get_next_index(text_path)
    
    # Build duplicate index with detailed status reporting
    db_index = build_duplicate_index_from_db()
    output_index = build_duplicate_index_from_outputs()
    duplicate_index = db_index + output_index
    
    print(f"🔎 Duplicate index ready: {len(db_index)} from db, {len(output_index)} from output → {len(duplicate_index)} total reference image(s)")

    # Calculate steps (skip last one as per original logic)
    max_steps = (duration - TEXT_START_SEC - IMAGE_OFFSET) // STEP_SEC
    total_steps_to_process = max(0, int(max_steps) - 1)

    print(f"Processing {total_steps_to_process} steps...")

    for step in range(total_steps_to_process):
        text_sec = TEXT_START_SEC + step * STEP_SEC
        img_sec = text_sec + IMAGE_OFFSET

        if img_sec >= duration:
            print(f"Skipping step {step} — image time {img_sec:.1f}s exceeds duration")
            break

        success = process_entry(video, text_sec, img_sec, index, text_path, duplicate_index)
        if success:
            index += 1

    # Cleanup temp files
    for f in (TEMP_TEXT_FRAME, TEMP_IMAGE_FRAME):
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

    print("🎉 DONE (last image + text combination skipped)")

    # Automatically run rewrite_extracted_text on the generated text file if available
    if _rewrite_mod is not None:
        try:
            print("\n🔁 Running rewrite_extracted_text on extracted text...")
            _rewrite_mod.process_file(text_path)
        except Exception as e:
            print(f"⚠️ rewrite_extracted_text failed: {e}")
    else:
        print("(rewrite_extracted_text module not available; skipping rewrite step)")

if __name__ == "__main__":
    main()