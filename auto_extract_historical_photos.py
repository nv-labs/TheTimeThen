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

# Some source videos have brief motion-blur / cross-fade transitions right at
# the fixed image_sec timestamp, producing a fuzzy/soft output photo. Instead
# of always grabbing the single frame at exactly img_sec, we sample a few
# nearby timestamps (within the photo's still-display window) and keep the
# sharpest one.
IMAGE_SEARCH_WINDOW_SEC = 2.0

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


def build_image_sample_timestamps(anchor_sec, search_window_sec=IMAGE_SEARCH_WINDOW_SEC):
    """Return a small set of candidate timestamps around anchor_sec, used to
    pick the sharpest available frame instead of trusting a single fixed
    instant (which can occasionally land on a motion-blurred / cross-fade
    transition frame).
    """
    start = max(0.0, anchor_sec - search_window_sec / 2.0)
    end = anchor_sec + search_window_sec / 2.0
    quarter = search_window_sec / 4.0
    values = [start, anchor_sec - quarter, anchor_sec, anchor_sec + quarter, end]

    out = []
    seen = set()
    for sec in values:
        normalized = round(max(0.0, float(sec)), 2)
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def quick_frame_score(image_bgr):
    """Higher score = sharper/more detailed frame. Combines local contrast
    (std dev) with a Laplacian-variance focus/sharpness measure, sampled from
    the central region of the frame (avoiding the caption-bar and edges).
    """
    h, w = image_bgr.shape[:2]
    if h < 16 or w < 16:
        return -1.0

    x1 = int(w * 0.18)
    x2 = int(w * 0.82)
    y1 = int(h * 0.05)
    y2 = int(h * 0.85)
    roi = image_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        roi = image_bgr

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    contrast_score = float(np.std(gray))
    sharpness_score = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    lit_ratio = float(np.count_nonzero(gray > 20)) / max(1, gray.size)
    return (contrast_score * 1.5) + (sharpness_score * 0.03) + (lit_ratio * 120.0)


def find_sharpest_image_frame(video, anchor_sec, out_file, search_window_sec=IMAGE_SEARCH_WINDOW_SEC):
    """Sample a few frames near anchor_sec and keep the sharpest one (written
    to out_file). Returns True on success, False if no frame could be read.
    """
    best_img = None
    best_score = -1.0
    for sec in build_image_sample_timestamps(anchor_sec, search_window_sec):
        if not extract_frame(video, sec, out_file):
            continue
        candidate = cv2.imread(out_file)
        if candidate is None:
            continue
        score = quick_frame_score(candidate)
        if score > best_score:
            best_score = score
            best_img = candidate

    if best_img is None:
        return False

    cv2.imwrite(out_file, best_img)
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


# ================= WATERMARK REMOVAL =================
# Some source videos overlay an "Old World Photos" watermark: white translucent
# text centered near the top of the frame, and/or gold script text on the left
# side of the frame (both sit on the static decorative border, never on the
# actual photo itself). Instead of cropping the frame, we detect these bright,
# locally-high-contrast text regions and inpaint over them using the
# surrounding background texture so the frame keeps its original size.
#
# Some videos also repeat the watermark a second time, tiled near the vertical
# middle of the frame -- right on top of the photo's subject. That instance is
# much harder to remove safely: any detector sensitive enough to pick up the
# very faint, low-contrast watermark text there also fires on real fine detail
# (hair, feathers, fabric texture, etc.), which would smudge genuine photo
# content. This extra "middle band" pass is therefore OFF by default and only
# runs when explicitly enabled, since it trades a chance of removing the
# leftover watermark for a small risk of blurring real detail in that region.
# Enable it by setting the environment variable WATERMARK_AGGRESSIVE=1
# (e.g. in .env) before running the script.

WATERMARK_TOP_BAND_RATIO = 0.16     # top strip (full width) checked for the centered overlay
WATERMARK_LEFT_BAND_X_RATIO = 0.24  # left strip width checked for the script-style watermark
WATERMARK_LEFT_BAND_Y_RANGE = (0.30, 0.72)  # vertical range (as ratio of height) of the left strip
WATERMARK_DIFF_THRESH = 10
WATERMARK_BLUR_KSIZE = 21

# Middle-band (opt-in, "aggressive") pass config
WATERMARK_MID_BAND_Y_RANGE = (0.38, 0.62)
WATERMARK_MID_DIFF_THRESH = 10
WATERMARK_MID_BLUR_KSIZE = 21
WATERMARK_MID_MAX_AREA_RATIO = 0.06  # if more than this fraction of the band would be
                                      # touched, assume it's real detail, not watermark,
                                      # and skip the middle-band pass for this frame.


def _watermark_aggressive_enabled():
    return str(os.environ.get("WATERMARK_AGGRESSIVE", "")).strip().lower() in ("1", "true", "yes", "on")


def _bright_text_mask(gray_full, x0, x1, y0, y1, diff_thresh=WATERMARK_DIFF_THRESH, blur_ksize=WATERMARK_BLUR_KSIZE):
    """Build a mask of bright, locally-contrasting pixels (likely overlay text)
    within the given region, by comparing each pixel to a blurred (local
    background) version of itself. Returns a full-size mask (same shape as
    gray_full) with the detected region filled in and everywhere else zero.
    """
    h, w = gray_full.shape
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    roi = gray_full[y0:y1, x0:x1]
    full_mask = np.zeros((h, w), dtype=np.uint8)
    if roi.size == 0:
        return full_mask

    k = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
    blur = cv2.GaussianBlur(roi, (k, k), 0)
    diff = cv2.subtract(roi, blur)
    _, roi_mask = cv2.threshold(diff, diff_thresh, 255, cv2.THRESH_BINARY)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    roi_mask = cv2.dilate(roi_mask, kernel, iterations=1)

    full_mask[y0:y1, x0:x1] = roi_mask
    return full_mask


def _mid_band_watermark_mask(gray):
    """Opt-in detection of a watermark instance tiled near the vertical middle
    of the frame. Uses a safety cap: if the detected region would cover too
    large a fraction of the band, it's more likely real photo detail than
    watermark text, so the whole candidate is discarded for that frame
    (better to leave a residual watermark than to smudge a real photo).
    """
    h, w = gray.shape
    y0 = int(h * WATERMARK_MID_BAND_Y_RANGE[0])
    y1 = int(h * WATERMARK_MID_BAND_Y_RANGE[1])
    mask = _bright_text_mask(
        gray, 0, w, y0, y1,
        diff_thresh=WATERMARK_MID_DIFF_THRESH,
        blur_ksize=WATERMARK_MID_BLUR_KSIZE,
    )
    band_area = max(1, (y1 - y0) * w)
    ratio = cv2.countNonZero(mask) / float(band_area)
    if ratio > WATERMARK_MID_MAX_AREA_RATIO:
        return np.zeros((h, w), dtype=np.uint8)
    return mask


def remove_watermark(img):
    """Remove the 'Old World Photos' style watermark (top-center overlay
    and/or left-side script text) by inpainting over detected text pixels
    using the surrounding background. Returns the (possibly) cleaned image;
    the image dimensions are never changed (no cropping).
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    top_mask = _bright_text_mask(gray, 0, w, 0, int(h * WATERMARK_TOP_BAND_RATIO))
    left_y0 = int(h * WATERMARK_LEFT_BAND_Y_RANGE[0])
    left_y1 = int(h * WATERMARK_LEFT_BAND_Y_RANGE[1])
    left_mask = _bright_text_mask(gray, 0, int(w * WATERMARK_LEFT_BAND_X_RATIO), left_y0, left_y1)

    mask = cv2.bitwise_or(top_mask, left_mask)

    if _watermark_aggressive_enabled():
        mid_mask = _mid_band_watermark_mask(gray)
        mask = cv2.bitwise_or(mask, mid_mask)

    if cv2.countNonZero(mask) == 0:
        return img

    return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)


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

    # Extract image frame: sample a small window around img_sec and keep the
    # sharpest frame, to avoid landing on a blurry transition/motion frame.
    if not find_sharpest_image_frame(video, img_sec, TEMP_IMAGE_FRAME):
        return False

    img = cv2.imread(TEMP_IMAGE_FRAME)
    if img is None:
        print(f"Failed to read image frame at {img_sec}s")
        return False

    img = remove_watermark(img)

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