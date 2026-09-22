import os
import re
import sys
import sqlite3
import io
import shutil
import hashlib
from datetime import datetime
from PIL import Image, UnidentifiedImageError

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# ================= CONFIG =================
DEFAULT_DB_PATH = r"D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\databases\image_collection.db"
DB_NAME = os.environ.get("THETIME_THEN_DB", DEFAULT_DB_PATH)
TABLE_NAME = "image_comp"
VISUAL_DUPLICATE_DISTANCE_THRESHOLD = 6

CATEGORIES = [
    "Actors",
    "Politicians",
    "Military",
    "Historical Events",
    "Places",
    "Cities",
    "Architecture",
    "Sports",
    "Science",
    "Technology",
    "Exploration",
    "Royalty",
    "Art",
    "Culture",
    "Everyday Life"
]
# =========================================


# ---------- DATABASE CONNECTION ----------
def connect_to_db(db_path=None):
    target_db = db_path or DB_NAME
    if not os.path.exists(target_db):
        print(f"❌ Database file '{target_db}' not found.")
        print("   Run your copy_photos_to_new_db.py script first to create it.")
        sys.exit(1)

    conn = sqlite3.connect(target_db)
    cursor = conn.cursor()

    # Check if the required table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,))
    if cursor.fetchone() is None:
        print(f"❌ Table '{TABLE_NAME}' does not exist in '{target_db}'.")
        print("   Expected table created by copy_photos_to_new_db.py.")
        print("   This script does NOT create tables — only inserts into existing ones.")
        sys.exit(1)

    print(f"✅ Connected to database '{target_db}' → table '{TABLE_NAME}' found.")
    return conn


# ---------- MAIN LOGIC ----------
def parse_descriptions(txt_path):
    entries = {}
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"(\d+)\s*\|\s*(.+)", line)
            if match:
                idx, text = match.groups()
                entries[idx] = text.strip()
    return entries


def find_image_for_index(image_dir, index):
    pattern = re.compile(rf"--{index}\.(png|jpg|jpeg)$", re.IGNORECASE)
    for name in os.listdir(image_dir):
        if pattern.search(name):
            return os.path.join(image_dir, name)
    return None


def cleanup_input_path(path_value):
    if os.path.isdir(path_value):
        shutil.rmtree(path_value)
        print(f"🗑️ Deleted folder: {path_value}")
    elif os.path.isfile(path_value):
        os.remove(path_value)
        print(f"🗑️ Deleted file: {path_value}")


def cleanup_parent_folder(file_path):
    parent_dir = os.path.dirname(os.path.abspath(file_path))
    if os.path.isdir(parent_dir):
        shutil.rmtree(parent_dir)
        print(f"🗑️ Deleted folder: {parent_dir}")


def compute_sha256(file_data):
    return hashlib.sha256(file_data).hexdigest()


def compute_pixel_sha256(file_data):
    if hasattr(Image, "Resampling"):
        resample_filter = Image.Resampling.LANCZOS
    else:
        resample_filter = Image.LANCZOS

    with Image.open(io.BytesIO(file_data)) as image:
        rgb = image.convert("RGB")
        arr = rgb.tobytes()
        shape_bytes = f"{rgb.size[0]}x{rgb.size[1]}".encode("utf-8")
        return hashlib.sha256(arr + shape_bytes).hexdigest()


def compute_dhash_from_image(image, hash_size=8):
    if hasattr(Image, "Resampling"):
        resample_filter = Image.Resampling.LANCZOS
    else:
        resample_filter = Image.LANCZOS

    grayscale = image.convert("L").resize((hash_size + 1, hash_size), resample_filter)
    pixels = list(grayscale.getdata())

    bit_string = []
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            bit_string.append("1" if left > right else "0")

    return format(int("".join(bit_string), 2), "016x")


def compute_ahash_from_image(image, hash_size=8):
    if hasattr(Image, "Resampling"):
        resample_filter = Image.Resampling.LANCZOS
    else:
        resample_filter = Image.LANCZOS

    grayscale = image.convert("L").resize((hash_size, hash_size), resample_filter)
    pixels = list(grayscale.getdata())
    avg = sum(pixels) / len(pixels)
    bits = ["1" if p >= avg else "0" for p in pixels]
    return format(int("".join(bits), 2), "016x")


def compute_hash_variants(file_data):
    with Image.open(io.BytesIO(file_data)) as image:
        image = image.convert("RGB")
        width, height = image.size
        if width == 0 or height == 0:
            return None

        top_h = max(1, int(height * 0.82))
        top_crop = image.crop((0, 0, width, top_h))

        x1 = int(width * 0.08)
        x2 = max(x1 + 1, int(width * 0.92))
        y1 = int(height * 0.08)
        y2 = max(y1 + 1, int(height * 0.92))
        center_crop = image.crop((x1, y1, x2, y2))

        dhashes = []
        ahashes = []
        for part in (image, top_crop, center_crop):
            dhashes.append(compute_dhash_from_image(part))
            ahashes.append(compute_ahash_from_image(part))

    return {
        "sha256": compute_sha256(file_data),
        "pixel_sha256": compute_pixel_sha256(file_data),
        "dhashes": dhashes,
        "ahashes": ahashes,
    }


def hamming_distance(hash_a, hash_b):
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def build_duplicate_index(cursor):
    cursor.execute(f"SELECT id, filename, file_data FROM {TABLE_NAME}")
    rows = cursor.fetchall()

    existing_filenames = set()
    existing_sha_index = {}
    existing_visual_index = []

    for row_id, filename, file_data in rows:
        existing_filenames.add(filename)

        if not file_data:
            continue

        try:
            variants = compute_hash_variants(file_data)
            if variants is None:
                continue
            if variants["sha256"] not in existing_sha_index:
                existing_sha_index[variants["sha256"]] = (row_id, filename)
            existing_visual_index.append(
                (
                    row_id,
                    filename,
                    variants["pixel_sha256"],
                    variants["dhashes"],
                    variants["ahashes"],
                )
            )
        except (UnidentifiedImageError, OSError, ValueError) as e:
            print(f"⚠️ Could not compute visual hash for existing row id={row_id}: {e}")

    return existing_filenames, existing_sha_index, existing_visual_index


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Insert extracted photos into the shared TheTimeThen database, "
                    "using a manually-specified category for ALL inserted photos "
                    "(no AI classification)."
    )
    parser.add_argument("image_dir", help="Folder containing extracted images")
    parser.add_argument("descriptions_file", help="Text file with numbered description entries")
    parser.add_argument(
        "category",
        help=f"Category to assign to every inserted photo. One of: {', '.join(CATEGORIES)} "
             "(any other value is accepted too, but won't match the standard category list)."
    )
    parser.add_argument("-test", "--test", type=int, help="Only insert the first N photos")
    parser.add_argument("--db", default=os.environ.get("THETIME_THEN_DB", DEFAULT_DB_PATH), help="SQLite database path to insert into")
    parser.add_argument("--keep-output", action="store_true", help="Keep the image folder and text-file parent folder after insertion")
    parser.add_argument("--force-category", action="store_true", help="Allow a category not in the standard CATEGORIES list without prompting")
    args = parser.parse_args()

    image_dir = args.image_dir
    desc_file = args.descriptions_file
    test_limit = args.test
    db_path = args.db
    category = args.category

    if category not in CATEGORIES and not args.force_category:
        print(f"⚠️ '{category}' is not in the standard category list: {', '.join(CATEGORIES)}")
        print("   Re-run with --force-category to use it anyway, or pick one of the standard categories.")
        sys.exit(1)

    if not os.path.isdir(image_dir):
        print(f"❌ Image directory not found: {image_dir}")
        sys.exit(1)

    if not os.path.isfile(desc_file):
        print(f"❌ Descriptions file not found: {desc_file}")
        sys.exit(1)

    descriptions = parse_descriptions(desc_file)
    if not descriptions:
        print("⚠️ No valid descriptions found in the text file.")
        sys.exit(1)

    conn = connect_to_db(db_path)
    cursor = conn.cursor()

    inserted = 0
    print("🔎 Building duplicate index from existing database rows...")
    existing_filenames, existing_sha_index, existing_visual_index = build_duplicate_index(cursor)
    print(
        f"✅ Duplicate index ready: filenames={len(existing_filenames)}, "
        f"exact_hashes={len(existing_sha_index)}, visual_hashes={len(existing_visual_index)}"
    )
    print(f"🏷️  Using manual category for all inserts: '{category}'")

    for index, text in descriptions.items():
        if test_limit and inserted >= test_limit:
            break

        image_path = find_image_for_index(image_dir, index)
        if not image_path:
            print(f"⚠️ No matching image for entry {index}, skipping...")
            continue

        filename = os.path.basename(image_path)

        try:
            with open(image_path, "rb") as f:
                file_data = f.read()
            with Image.open(io.BytesIO(file_data)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as e:
            print(f"❌ Invalid/corrupted image {filename}: {e}")
            continue

        if filename in existing_filenames:
            print(f"⏭️  Skipped {filename} — already exists in database")
            continue

        try:
            candidate_variants = compute_hash_variants(file_data)
        except (UnidentifiedImageError, OSError, ValueError) as e:
            print(f"❌ Could not compute visual hash for {filename}: {e}")
            continue

        if candidate_variants is None:
            print(f"❌ Could not compute visual hash for {filename}")
            continue

        file_sha = candidate_variants["sha256"]
        if file_sha in existing_sha_index:
            existing_id, existing_filename = existing_sha_index[file_sha]
            print(
                f"⏭️  Skipped {filename} — exact duplicate of existing id={existing_id} "
                f"({existing_filename})"
            )
            continue

        similar_row = None
        for (
            existing_id,
            existing_filename,
            existing_pixel_sha,
            existing_dhashes,
            existing_ahashes,
        ) in existing_visual_index:
            if (
                candidate_variants["pixel_sha256"]
                and existing_pixel_sha
                and candidate_variants["pixel_sha256"] == existing_pixel_sha
            ):
                similar_row = (existing_id, existing_filename, 0)
                break

            for candidate_dhash in candidate_variants["dhashes"]:
                for existing_dhash in existing_dhashes:
                    distance = hamming_distance(candidate_dhash, existing_dhash)
                    if distance <= VISUAL_DUPLICATE_DISTANCE_THRESHOLD:
                        similar_row = (existing_id, existing_filename, distance)
                        break
                if similar_row is not None:
                    break
            if similar_row is not None:
                break

            for candidate_ahash in candidate_variants["ahashes"]:
                for existing_ahash in existing_ahashes:
                    distance = hamming_distance(candidate_ahash, existing_ahash)
                    if distance <= VISUAL_DUPLICATE_DISTANCE_THRESHOLD:
                        similar_row = (existing_id, existing_filename, distance)
                        break
                if similar_row is not None:
                    break
            if similar_row is not None:
                break

        if similar_row is not None:
            existing_id, existing_filename, distance = similar_row
            print(
                f"⏭️  Skipped {filename} — visually similar to existing id={existing_id} "
                f"({existing_filename}), distance={distance}"
            )
            continue

        try:
            cursor.execute(f"""
                INSERT INTO {TABLE_NAME} (
                    filename, file_size, file_data, source_url,
                    file_type, added_date, xml_title, description, xml_subject
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename,
                len(file_data),
                file_data,
                image_path,
                os.path.splitext(filename)[1][1:].lower(),
                datetime.now(),
                filename,
                text,
                category
            ))
            conn.commit()
            inserted_id = cursor.lastrowid
            existing_filenames.add(filename)
            existing_sha_index[file_sha] = (inserted_id, filename)
            existing_visual_index.append(
                (
                    inserted_id,
                    filename,
                    candidate_variants["pixel_sha256"],
                    candidate_variants["dhashes"],
                    candidate_variants["ahashes"],
                )
            )
            inserted += 1
            print(f"✅ Inserted {filename} → {category}")
        except sqlite3.Error as e:
            print(f"❌ Failed to insert {filename}: {e}")

    conn.close()
    if not args.keep_output:
        cleanup_input_path(image_dir)
        cleanup_parent_folder(desc_file)
    print(f"\n🎉 DONE — Successfully inserted {inserted} new photos into '{TABLE_NAME}' table with category '{category}'.")


if __name__ == "__main__":
    main()
