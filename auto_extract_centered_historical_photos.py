import argparse
import ctypes
import hashlib
import os
import pickle
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from difflib import SequenceMatcher

import cv2
import numpy as np
import pytesseract
from collections import deque
from pytesseract import Output

try:
    from batch_remove_background import crop_to_foreground_panel
except Exception:
    crop_to_foreground_panel = None

try:
    import rewrite_extracted_text as _rewrite_mod
except Exception:
    _rewrite_mod = None

FFMPEG_PATH = shutil.which("ffmpeg") or r"C:\ffmpeg\ffmpeg-8.0.1-essentials_build\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"
FFPROBE_PATH = shutil.which("ffprobe") or r"C:\ffmpeg\ffmpeg-8.0.1-essentials_build\ffmpeg-8.0.1-essentials_build\bin\ffprobe.exe"
TESSERACT_PATH = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

OUTPUT_DIR = "output"
TEXT_FILE = "centered_extracted_text.txt"
TEMP_FRAME = "_centered_frame.jpg"
EXTRA_DUPLICATE_DIRS = ("output-ready", "Output")
DB_NAME = "image_collection.db"
DB_TABLE_NAME = "image_comp"
VISUAL_DUPLICATE_DISTANCE_THRESHOLD = 6
DUPLICATE_CACHE_FILE = ".centered_duplicate_index_cache.pkl"
LARGE_DB_AUTO_SKIP_BYTES = 500 * 1024 * 1024

START_SEC = 0.0
STEP_SEC = 12.0
SEARCH_WINDOW_SEC = 4.0
TEXT_OFFSET_SEC = 9.0
TEXT_SEARCH_WINDOW_SEC = 4.0
MAX_SUMMARY_WORDS = 4

STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "and", "or", "to", "with",
    "photo", "image", "picture", "signed", "by", "from", "was", "were",
    "is", "are", "this", "that", "last", "stretch", "all", "videos"
}


def resolve_media_path_for_ffmpeg(path):
    if os.name != "nt":
        return path
    if all(ord(ch) < 128 for ch in path):
        return path
    try:
        get_short = ctypes.windll.kernel32.GetShortPathNameW
        needed = get_short(path, None, 0)
        if needed <= 0:
            return path
        buf = ctypes.create_unicode_buffer(needed)
        get_short(path, buf, needed)
        short_path = buf.value
        if short_path and os.path.exists(short_path):
            return short_path
    except Exception:
        return path
    return path


def prepare_ffmpeg_video_input(video_path):
    resolved = resolve_media_path_for_ffmpeg(video_path)
    probe_cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        resolved,
    ]
    probe = subprocess.run(probe_cmd, capture_output=True, text=True, encoding="utf-8")
    if probe.returncode == 0 and probe.stdout.strip():
        return resolved, None

    base_dir = os.path.dirname(video_path) or os.getcwd()
    ext = os.path.splitext(video_path)[1] or ".mp4"
    alias_name = f"_ffmpeg_input_{abs(hash(video_path)) % 10**10}{ext}"
    alias_path = os.path.join(base_dir, alias_name)

    if not os.path.exists(alias_path):
        try:
            os.link(video_path, alias_path)
        except OSError:
            shutil.copy2(video_path, alias_path)
    return alias_path, alias_path


def get_video_duration(video_path):
    cmd = [
        FFPROBE_PATH,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
        duration_str = result.stdout.strip()
        if not duration_str:
            raise ValueError("ffprobe returned empty duration")
        return float(duration_str)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed (code {e.returncode}):\n{e.stderr.strip()}")
    except FileNotFoundError:
        raise RuntimeError(f"ffprobe not found at: {FFPROBE_PATH}")
    except ValueError as e:
        raise RuntimeError(f"Could not parse duration: {e}")


def extract_frame(video, second, out_file):
    cmd = [FFMPEG_PATH, "-y", "-ss", str(second), "-i", video, "-frames:v", "1", "-q:v", "2", out_file]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return os.path.exists(out_file)


def file_signature(path):
    if not os.path.exists(path):
        return None
    stat = os.stat(path)
    return {
        "path": os.path.abspath(path),
        "size": int(stat.st_size),
        "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1000000000))),
    }


def load_duplicate_cache(cache_path):
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "rb") as f:
            data = pickle.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_duplicate_cache(cache_path, cache_data):
    tmp_path = f"{cache_path}.tmp"
    with open(tmp_path, "wb") as f:
        pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp_path, cache_path)


def has_valid_db_duplicate_cache():
    db_sig = file_signature(DB_NAME)
    if db_sig is None:
        return False
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DUPLICATE_CACHE_FILE)
    cache_data = load_duplicate_cache(cache_path)
    db_cache = cache_data.get("db")
    return bool(db_cache and db_cache.get("signature") == db_sig and isinstance(db_cache.get("entries"), list))


def get_rewrite_skip_reason():
    if _rewrite_mod is None:
        return "rewrite_extracted_text module not available"

    resolve_key = getattr(_rewrite_mod, "_resolve_api_key", None)
    if not callable(resolve_key):
        return None

    api_key = (resolve_key() or "").strip()
    if not api_key:
        return "OPENAI_API_KEY is not configured"
    if "your-key-here" in api_key.lower():
        return "OPENAI_API_KEY is still the placeholder value"
    return None


def crop_caption_region(img):
    h, w = img.shape[:2]
    y_start = int(h * 0.68)
    return img[y_start:h, 0:w]


def estimate_border_color(img):
    h, w = img.shape[:2]
    border = []
    border.append(img[:max(1, h // 20), :, :].reshape(-1, 3))
    border.append(img[h - max(1, h // 20):, :, :].reshape(-1, 3))
    border.append(img[:, :max(1, w // 20), :].reshape(-1, 3))
    border.append(img[:, w - max(1, w // 20):, :].reshape(-1, 3))
    all_border = np.concatenate(border, axis=0)
    if all_border.size == 0:
        return np.array([0, 0, 0], dtype=np.uint8)
    return np.median(all_border, axis=0).astype(np.uint8)


def border_connected_background_mask(image_bgr, threshold=22.0):
    h, w = image_bgr.shape[:2]
    bg_color = estimate_border_color(image_bgr)
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    border_vals = gray.reshape(-1)
    # use a darker background estimate; then threshold on distance from border color
    dist = np.linalg.norm(image_bgr.astype(np.float32) - bg_color[None, None, :], axis=2)
    candidate = dist <= threshold

    visited = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        if candidate[0, x]:
            q.append((0, x)); visited[0, x] = True
        if candidate[h - 1, x] and not visited[h - 1, x]:
            q.append((h - 1, x)); visited[h - 1, x] = True
    for y in range(h):
        if candidate[y, 0] and not visited[y, 0]:
            q.append((y, 0)); visited[y, 0] = True
        if candidate[y, w - 1] and not visited[y, w - 1]:
            q.append((y, w - 1)); visited[y, w - 1] = True

    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and candidate[ny, nx]:
                visited[ny, nx] = True
                q.append((ny, nx))

    background = np.zeros((h, w), dtype=np.uint8)
    background[visited] = 255
    return background


def detect_ocr_text_mask(image_bgr):
    h, w = image_bgr.shape[:2]
    if h < 30 or w < 30:
        return np.zeros((h, w), dtype=np.uint8)

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    try:
        data = pytesseract.image_to_data(gray, config="--oem 3 --psm 6", output_type=Output.DICT)
    except Exception:
        return np.zeros((h, w), dtype=np.uint8)

    mask = np.zeros((h, w), dtype=np.uint8)
    bottom_y = 0
    for i, text in enumerate(data.get("text", [])):
        txt = str(text).strip()
        if not txt:
            continue
        try:
            conf = int(data["conf"][i])
        except Exception:
            conf = 0
        if conf < 0:
            conf = 0
        if conf < 15:
            continue

        x = int(data["left"][i])
        y = int(data["top"][i])
        ww = int(data["width"][i])
        hh = int(data["height"][i])
        if y < int(h * 0.35):
            continue
        if ww < 12 or hh < 8:
            continue
        pad = 4
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w, x + ww + pad)
        y1 = min(h, y + hh + pad)
        cv2.rectangle(mask, (x0, y0), (x1, y1), 255, -1)
        bottom_y = max(bottom_y, y1)

    if bottom_y == 0:
        return np.zeros((h, w), dtype=np.uint8)

    return mask


def detect_bottom_overlay_start(mask, image_height):
    if mask is None or mask.size == 0:
        return None

    row_coverage = np.mean(mask > 0, axis=1)
    candidate_rows = np.where(row_coverage >= 0.015)[0]
    if candidate_rows.size == 0:
        candidate_rows = np.where(np.any(mask > 0, axis=1))[0]
    if candidate_rows.size == 0:
        return None

    candidate_rows = candidate_rows[candidate_rows >= int(image_height * 0.55)]
    if candidate_rows.size == 0:
        return None

    runs = []
    run_start = int(candidate_rows[0])
    prev = int(candidate_rows[0])
    for row in candidate_rows[1:]:
        row = int(row)
        if row <= prev + 3:
            prev = row
            continue
        runs.append((run_start, prev))
        run_start = row
        prev = row
    runs.append((run_start, prev))

    near_bottom_runs = [run for run in runs if run[1] >= int(image_height * 0.74)]
    if not near_bottom_runs:
        return None

    start, _ = min(near_bottom_runs, key=lambda run: run[0])
    return start


def remove_text_overlay(image_bgr):
    if image_bgr is None or image_bgr.size == 0:
        return image_bgr

    h, w = image_bgr.shape[:2]
    text_mask = detect_ocr_text_mask(image_bgr)
    if np.count_nonzero(text_mask) == 0:
        return image_bgr

    overlay_start = detect_bottom_overlay_start(text_mask, h)
    if overlay_start is None:
        return image_bgr

    top_margin = max(4, int(h * 0.012))
    cut = max(int(h * 0.72), overlay_start - top_margin)
    if cut >= h - 8:
        return image_bgr
    return image_bgr[:cut, :]


def crop_center_photo(img):
    if img is None or img.size == 0:
        return img

    h, w = img.shape[:2]

    if crop_to_foreground_panel is not None:
        try:
            crop = crop_to_foreground_panel(
                img,
                threshold=18.0,
                pad_x_ratio=0.04,
                pad_y_ratio=0.0,
                inset_x_ratio=0.0,
                inset_y_ratio=0.0,
                crop_vertical=False,
            )
            if crop is not None and crop.size > 0 and min(crop.shape[:2]) > 16:
                crop = remove_text_overlay(crop)
                return crop
        except Exception:
            pass

    try:
        bg_mask = border_connected_background_mask(img, threshold=22.0)
        subject_mask = cv2.bitwise_not(bg_mask)
        if np.count_nonzero(subject_mask) > (h * w * 0.05):
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(subject_mask, connectivity=8)
            best_label = 0
            best_area = -1
            cy, cx = h // 2, w // 2
            for label in range(1, num_labels):
                area = stats[label, cv2.CC_STAT_AREA]
                if area <= 0:
                    continue
                x = stats[label, cv2.CC_STAT_LEFT]
                y = stats[label, cv2.CC_STAT_TOP]
                ww = stats[label, cv2.CC_STAT_WIDTH]
                hh = stats[label, cv2.CC_STAT_HEIGHT]
                center_dist = abs((x + ww / 2.0) - cx) + abs((y + hh / 2.0) - cy)
                score = area - center_dist * 0.3
                if score > best_area:
                    best_area = score
                    best_label = label
            if best_label > 0:
                ys, xs = np.where(labels == best_label)
                if len(xs) > 0:
                    x_pad = max(10, int(w * 0.05))
                    x0 = max(0, int(xs.min()) - x_pad)
                    x1 = min(w - 1, int(xs.max()) + x_pad)
                    crop = img[:, x0:x1 + 1]
                    if crop.size > 0 and min(crop.shape[:2]) > 16:
                        crop = remove_text_overlay(crop)
                        return crop
    except Exception:
        pass

    x1 = int(w * 0.10)
    x2 = int(w * 0.90)
    y1 = int(h * 0.03)
    y2 = int(h * 0.88)
    crop = img[y1:y2, x1:x2]
    crop = remove_text_overlay(crop)
    return crop


def clean_ocr_text(text):
    text = text.replace("\n", " ").strip()
    text = re.sub(r"^[^A-Za-z]{1,20}", "", text)
    text = re.sub(r"^\d+\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()



def normalize_caption_for_compare(text):
    if not text:
        return ""
    normalized = text.lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def caption_similarity(text_a, text_b):
    a = normalize_caption_for_compare(text_a)
    b = normalize_caption_for_compare(text_b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    seq_ratio = SequenceMatcher(None, a, b).ratio()
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    union = tokens_a | tokens_b
    jaccard = (len(tokens_a & tokens_b) / float(len(union))) if union else 0.0
    return max(seq_ratio, jaccard)


def captions_too_similar(text_a, text_b, threshold=0.88):
    sim = caption_similarity(text_a, text_b)
    if sim >= threshold:
        return True

    a = normalize_caption_for_compare(text_a)
    b = normalize_caption_for_compare(text_b)
    if not a or not b:
        return False

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 12 and shorter in longer:
        return True

    if sim >= 0.76:
        return True

    stop = {"a", "an", "the", "in", "on", "of", "and", "to", "from", "with", "at", "is", "was", "are"}
    tokens_a = {tok for tok in a.split() if tok not in stop and len(tok) > 2}
    tokens_b = {tok for tok in b.split() if tok not in stop and len(tok) > 2}
    shared = tokens_a & tokens_b
    years_a = set(re.findall(r"(?:18|19|20)\d{2}", a))
    years_b = set(re.findall(r"(?:18|19|20)\d{2}", b))

    if years_a and years_b and (years_a & years_b) and len(shared) >= 2:
        if len(tokens_a) <= 7 or len(tokens_b) <= 7:
            return True

    return False

def build_sample_timestamps(anchor_sec, search_window_sec):
    start = max(0.0, anchor_sec - search_window_sec / 2.0)
    end = anchor_sec + search_window_sec / 2.0
    if search_window_sec <= 4.0:
        values = [start, anchor_sec, end]
    else:
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


def caption_text_score(text):
    if not text:
        return -1.0
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return -1.0

    letters = sum(1 for ch in text if ch.isalpha())
    if letters < 6:
        return -1.0

    long_words = sum(1 for w in words if len(w) >= 4)
    short_words = sum(1 for w in words if len(w) == 1)
    vowels = sum(1 for ch in text.lower() if ch in "aeiou")
    vowel_ratio = (vowels / float(letters)) if letters else 0.0

    score = (len(words) * 2.0) + (long_words * 1.5) - (short_words * 1.2)
    if 0.18 <= vowel_ratio <= 0.55:
        score += 2.0
    return score


def ocr_caption(img):
    caption = crop_caption_region(img)
    gray = cv2.cvtColor(caption, cv2.COLOR_BGR2GRAY)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    gray = cv2.bilateralFilter(gray, 7, 50, 50)
    gray = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        5,
    )
    try:
        raw = pytesseract.image_to_string(gray, config="--oem 3 --psm 6")
    except Exception:
        return ""
    text = clean_ocr_text(raw)
    if caption_text_score(text) < 2.0:
        return ""
    return text


def extract_best_caption_text(video, anchor_sec, search_window_sec=TEXT_SEARCH_WINDOW_SEC):
    best_text = ""
    best_sec = anchor_sec
    best_score = -1.0

    for sec in build_sample_timestamps(anchor_sec, search_window_sec):
        if not extract_frame(video, float(sec), TEMP_FRAME):
            continue
        img = cv2.imread(TEMP_FRAME)
        if img is None:
            continue

        text = ocr_caption(img)
        score = caption_text_score(text)
        if score > best_score:
            best_score = score
            best_text = text
            best_sec = float(sec)

    return best_text, best_sec


def quick_frame_score(image_bgr):
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
    detail_score = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    lit_ratio = float(np.count_nonzero(gray > 20)) / max(1, gray.size)
    return (contrast_score * 1.5) + (detail_score * 0.03) + (lit_ratio * 120.0)


def summarize_text(text, max_words=4):
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return "image"
    lower = [w.lower() for w in words]
    years = [w for w in lower if re.fullmatch(r"(18|19|20)\d{2}", w)]
    proper = [w.lower() for w in words if w[0].isupper() and w.lower() not in STOPWORDS]
    keywords = [w for w in lower if w not in STOPWORDS and len(w) > 3]
    scored = Counter()
    for w in years:
        scored[w] += 5
    for w in proper:
        scored[w] += 4
    for w in keywords:
        scored[w] += 1
    summary = [w for w, _ in scored.most_common(max_words)]
    return "_".join(summary) if summary else "image"


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


def compute_dhash_from_image(img, hash_size=8):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = "".join("1" if v else "0" for v in diff.flatten())
    return format(int(bits, 2), "016x")


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
    center_crop = crop_center_photo(img)
    variants = [full, center_crop]
    dhashes = []
    ahashes = []
    for part in variants:
        if part is None or part.size == 0:
            continue
        dhashes.append(compute_dhash_from_image(part))
        ahashes.append(compute_ahash_from_image(part))
    return {
        "sha256": hashlib.sha256(cv2.imencode(".png", full)[1].tobytes()).hexdigest(),
        "pixel_sha256": hashlib.sha256(cv2.cvtColor(full, cv2.COLOR_BGR2RGB).tobytes() + f"{w}x{h}".encode("utf-8")).hexdigest(),
        "dhashes": dhashes,
        "ahashes": ahashes,
    }


def decode_blob_to_image(file_data):
    np_data = np.frombuffer(file_data, dtype=np.uint8)
    return cv2.imdecode(np_data, cv2.IMREAD_COLOR)


def build_duplicate_index_from_db():
    if not os.path.exists(DB_NAME):
        return []
    db_sig = file_signature(DB_NAME)
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DUPLICATE_CACHE_FILE)
    cache_data = load_duplicate_cache(cache_path)
    db_cache = cache_data.get("db")
    if db_cache and db_cache.get("signature") == db_sig and isinstance(db_cache.get("entries"), list):
        print(f"[INFO] Loaded {len(db_cache['entries'])} cached duplicate refs from DB.")
        return db_cache["entries"]

    start_time = time.perf_counter()
    print("[INFO] Building duplicate refs from DB (first run may take a while)...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (DB_TABLE_NAME,))
    if cursor.fetchone() is None:
        conn.close()
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
        index.append({
            "source": "db",
            "id": row_id,
            "name": filename or f"id_{row_id}",
            "sha256": hashes["sha256"],
            "pixel_sha256": hashes["pixel_sha256"],
            "dhashes": hashes["dhashes"],
            "ahashes": hashes["ahashes"],
        })
    cache_data["db"] = {
        "signature": db_sig,
        "entries": index,
    }
    try:
        save_duplicate_cache(cache_path, cache_data)
    except OSError:
        pass
    print(f"[INFO] Built {len(index)} duplicate refs from DB in {time.perf_counter() - start_time:.1f}s.")
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
        index.append({
            "source": "output",
            "id": None,
            "name": name,
            "sha256": hashes["sha256"],
            "pixel_sha256": hashes["pixel_sha256"],
            "dhashes": hashes["dhashes"],
            "ahashes": hashes["ahashes"],
        })
    return index


def build_duplicate_index_from_outputs():
    index = []
    seen = set()
    for folder in (OUTPUT_DIR,) + EXTRA_DUPLICATE_DIRS:
        abs_path = os.path.abspath(folder)
        if abs_path in seen:
            continue
        seen.add(abs_path)
        index.extend(build_duplicate_index_from_dir(folder))
    return index


def check_visual_duplicate(img, duplicate_index):
    candidate = compute_hash_variants(img)
    if candidate is None:
        return None
    for entry in duplicate_index:
        if candidate["pixel_sha256"] and entry["pixel_sha256"] and candidate["pixel_sha256"] == entry["pixel_sha256"]:
            return {"type": "exact", "entry": entry, "distance": 0}
        if candidate["sha256"] and entry["sha256"] and candidate["sha256"] == entry["sha256"]:
            return {"type": "exact", "entry": entry, "distance": 0}
        for c_dhash in candidate["dhashes"]:
            for e_dhash in entry["dhashes"]:
                distance = hamming_distance(c_dhash, e_dhash)
                if distance <= VISUAL_DUPLICATE_DISTANCE_THRESHOLD:
                    return {"type": "visual", "entry": entry, "distance": distance}
        for c_ahash in candidate["ahashes"]:
            for e_ahash in entry["ahashes"]:
                distance = hamming_distance(c_ahash, e_ahash)
                if distance <= VISUAL_DUPLICATE_DISTANCE_THRESHOLD:
                    return {"type": "visual", "entry": entry, "distance": distance}
    return None


def add_image_to_duplicate_index(img, name, duplicate_index):
    hashes = compute_hash_variants(img)
    if hashes is None:
        return
    duplicate_index.append({
        "source": "output",
        "id": None,
        "name": name,
        "sha256": hashes["sha256"],
        "pixel_sha256": hashes["pixel_sha256"],
        "dhashes": hashes["dhashes"],
        "ahashes": hashes["ahashes"],
    })


def find_best_frame_for_step(video, anchor_sec, search_window_sec=SEARCH_WINDOW_SEC):
    best = None
    best_score = -1
    for sec in build_sample_timestamps(anchor_sec, search_window_sec):
        if not extract_frame(video, float(sec), TEMP_FRAME):
            continue
        img = cv2.imread(TEMP_FRAME)
        if img is None:
            continue
        score = quick_frame_score(img)
        if score > best_score:
            best = {"sec": float(sec), "text": "", "image": img.copy()}
            best_score = score
    if best is None:
        return None

    photo = crop_center_photo(best["image"])
    if photo is None or photo.size == 0:
        return None
    return {"sec": best["sec"], "text": "", "photo": photo}


def process_entry(video, second, index, text_path, duplicate_index, text_offset_sec, text_search_window_sec,
                  prev_text=None, prev_text_sec=None, step_sec=STEP_SEC):
    """Extract one photo+caption entry.

    Returns (True, used_text, used_text_sec) on success, (False, prev_text, prev_text_sec) on skip/fail.
    Thread prev_text/prev_text_sec through consecutive calls so stale carry-over captions are detected.
    """
    frame = find_best_frame_for_step(video, second)
    if frame is None:
        return False, prev_text, prev_text_sec

    prev_key = prev_text if prev_text else None
    base_anchor = max(0.0, frame["sec"] - text_offset_sec)
    anchor_shifts = [0.0, 3.0, 6.0, 9.0, 12.0]
    best_any = None
    best_non_prev = None

    for shift in anchor_shifts:
        candidate_anchor = base_anchor + shift
        text, text_sec = extract_best_caption_text(video, candidate_anchor, search_window_sec=text_search_window_sec)
        score = caption_text_score(text)
        if score < 2.0:
            continue

        candidate = (text, text_sec, score)

        if best_any is None or score > best_any[2]:
            best_any = candidate

        if prev_key and captions_too_similar(text, prev_key):
            continue

        if best_non_prev is None or score > best_non_prev[2]:
            best_non_prev = candidate

    if best_non_prev is not None:
        text, text_sec, _ = best_non_prev
    elif best_any is not None:
        text, text_sec, _ = best_any
    else:
        text = ""
        text_sec = base_anchor

    # Final safeguard: if the chosen text still matches the previous frame and it comes from the same
    # caption time span, drop it rather than writing a duplicate caption for a different image.
    if text and prev_key and captions_too_similar(text, prev_key):
        if prev_text_sec is None or text_sec < prev_text_sec + step_sec:
            print(f"[WARN] #{index} carry-over caption detected (text_sec={text_sec:.1f}s matches prev at {prev_text_sec}), clearing text")
            text = ""

    if not text:
        text = frame["text"] if frame["text"] else "image"
        text_sec = frame["sec"]

    photo = frame["photo"]
    duplicate_hit = check_visual_duplicate(photo, duplicate_index)
    if duplicate_hit is not None:
        hit = duplicate_hit["entry"]
        if duplicate_hit["type"] == "exact":
            print(f"[SKIP] #{index} exact duplicate vs {hit['source']}:{hit['name']}")
        else:
            print(f"[SKIP] #{index} visual duplicate (d={duplicate_hit['distance']}) vs {hit['source']}:{hit['name']}")
        return False, prev_text, prev_text_sec

    summary = summarize_text(text, MAX_SUMMARY_WORDS)
    filename = f"{summary}--{index}.png"
    output_path = os.path.join(OUTPUT_DIR, filename)

    with open(text_path, "a", encoding="utf-8") as f:
        f.write(f"{index} | {text}\n")

    cv2.imwrite(output_path, photo)
    add_image_to_duplicate_index(photo, filename, duplicate_index)
    print(f"[OK] #{index} image={frame['sec']:.1f}s text={text_sec:.1f}s -> {filename} text={text[:90]}")
    # Only propagate a real caption (not the 'image' fallback) as prev_text
    real_text = text if text != "image" else None
    real_sec = text_sec if real_text else None
    return True, real_text, real_sec

def main():
    parser = argparse.ArgumentParser(description="Extract centered historical-photos from slideshow videos.")
    parser.add_argument("video", help="Path to the source video")
    parser.add_argument("--start-sec", type=float, default=START_SEC, help="Start timestamp for extraction in seconds")
    parser.add_argument("--step-sec", type=float, default=STEP_SEC, help="Gap between extraction anchors in seconds")
    parser.add_argument("--search-window", type=float, default=SEARCH_WINDOW_SEC, help="Look around each anchor +/- window seconds for the clearest frame")
    parser.add_argument("--text-offset-sec", type=float, default=TEXT_OFFSET_SEC, help="Read caption text from this many seconds before the selected image frame (default: 9.0).")
    parser.add_argument("--text-search-window", type=float, default=TEXT_SEARCH_WINDOW_SEC, help="Search window around text timestamp for the cleanest OCR result.")
    parser.add_argument("--duplicate-scope", choices=["auto", "all", "output", "none"], default="auto", help="Duplicate check scope. 'auto' skips the large DB scan when image_collection.db is huge.")
    parser.add_argument("--skip-rewrite", action="store_true", help="Skip rewrite_extracted_text post-processing.")
    parser.add_argument("--max-frames", type=int, default=0, help="Optional max frames to process (0 = unlimited)")
    args = parser.parse_args()

    video = args.video
    if not os.path.isfile(video):
        print(f"Error: file not found: {video}")
        sys.exit(1)
    video_input, temp_video_alias = prepare_ffmpeg_video_input(video)
    if temp_video_alias is not None:
        print(f"[INFO] Using ffmpeg-safe alias: {os.path.basename(video_input)}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    text_path = os.path.join(OUTPUT_DIR, TEXT_FILE)
    index = get_next_index(text_path)

    try:
        duration = get_video_duration(video_input)
    except Exception as e:
        print(f"Error getting duration: {e}")
        sys.exit(1)

    duplicate_scope = args.duplicate_scope
    if duplicate_scope == "auto":
        db_sig = file_signature(DB_NAME)
        if db_sig and db_sig["size"] >= LARGE_DB_AUTO_SKIP_BYTES and not has_valid_db_duplicate_cache():
            duplicate_scope = "output"
            print("[INFO] Auto duplicate scope: skipping DB duplicate scan for speed. Use --duplicate-scope all to re-enable it.")
        else:
            duplicate_scope = "all"

    db_index = []
    output_index = []
    if duplicate_scope == "all":
        db_index = build_duplicate_index_from_db()
        output_index = build_duplicate_index_from_outputs()
    elif duplicate_scope == "output":
        output_index = build_duplicate_index_from_outputs()
    elif duplicate_scope == "none":
        pass
    duplicate_index = db_index + output_index
    print(f"Video duration: {duration:.2f}s")
    print(f"Duplicate refs: {len(db_index)} from db, {len(output_index)} from output, {len(duplicate_index)} total")

    processed = 0
    anchor = args.start_sec
    prev_text = None
    prev_text_sec = None
    step = args.step_sec
    while anchor < duration - 1:
        if args.max_frames and processed >= args.max_frames:
            break
        result, prev_text, prev_text_sec = process_entry(
            video_input,
            anchor,
            index,
            text_path,
            duplicate_index,
            text_offset_sec=max(0.0, float(args.text_offset_sec)),
            text_search_window_sec=max(0.5, float(args.text_search_window)),
            prev_text=prev_text,
            prev_text_sec=prev_text_sec,
            step_sec=step,
        )
        if result:
            index += 1
            processed += 1
        anchor += step

    if os.path.exists(TEMP_FRAME):
        try:
            os.remove(TEMP_FRAME)
        except OSError:
            pass
    if temp_video_alias is not None and os.path.exists(temp_video_alias):
        try:
            os.remove(temp_video_alias)
        except OSError:
            pass

    print(f"[DONE] processed {processed} frame(s)")
    rewrite_skip_reason = "disabled by --skip-rewrite" if args.skip_rewrite else get_rewrite_skip_reason()
    if rewrite_skip_reason is None:
        try:
            print("\n[INFO] Running rewrite_extracted_text on extracted text...")
            _rewrite_mod.process_file(text_path)
        except Exception as e:
            print(f"[WARN] rewrite_extracted_text failed: {e}")
    else:
        print(f"[INFO] Skipping rewrite_extracted_text: {rewrite_skip_reason}")


if __name__ == "__main__":
    main()


