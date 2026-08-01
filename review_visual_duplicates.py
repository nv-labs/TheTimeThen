import argparse
import csv
import io
import os
import re
import sqlite3
import sys
from datetime import datetime

from PIL import Image, UnidentifiedImageError

# ================= CONFIG =================
DB_NAME = "image_collection.db"
TABLE_NAME = "image_comp"
DEFAULT_OUTPUT_DIR = "duplicate_review"
DEFAULT_DISTANCE_THRESHOLD = 4
# =========================================


def connect_to_db():
    if not os.path.exists(DB_NAME):
        print(f"ERROR: Database file '{DB_NAME}' not found.")
        sys.exit(1)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,))
    if cursor.fetchone() is None:
        print(f"ERROR: Table '{TABLE_NAME}' does not exist in '{DB_NAME}'.")
        conn.close()
        sys.exit(1)

    print(f"Connected to database '{DB_NAME}' -> table '{TABLE_NAME}'")
    return conn


def compute_dhash(file_data, hash_size=8):
    if hasattr(Image, "Resampling"):
        resample_filter = Image.Resampling.LANCZOS
    else:
        resample_filter = Image.LANCZOS

    with Image.open(io.BytesIO(file_data)) as image:
        grayscale = image.convert("L").resize((hash_size + 1, hash_size), resample_filter)
        pixels = list(grayscale.getdata())

    bits = []
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            bits.append("1" if left > right else "0")

    return format(int("".join(bits), 2), "016x")


def hamming_distance(hash_a, hash_b):
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def sanitize_filename(name):
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    safe = safe.strip().strip(".")
    return safe or "unnamed"


def load_records(cursor):
    cursor.execute(
        f"""
        SELECT id, filename, file_data, added_date, description, xml_subject
        FROM {TABLE_NAME}
        ORDER BY id
        """
    )
    rows = cursor.fetchall()
    records = []

    for row in rows:
        rec_id, filename, file_data, added_date, description, xml_subject = row
        if not file_data:
            print(f"WARN: id={rec_id} has empty image data, skipping.")
            continue

        try:
            dhash = compute_dhash(file_data)
        except (UnidentifiedImageError, OSError, ValueError) as err:
            print(f"WARN: id={rec_id} ({filename}) invalid image data: {err}")
            continue

        records.append(
            {
                "id": rec_id,
                "filename": filename or f"id_{rec_id}",
                "file_data": file_data,
                "added_date": added_date,
                "description": description,
                "xml_subject": xml_subject,
                "dhash": dhash,
            }
        )

    print(f"Loaded {len(records)} valid images from DB.")
    return records


def find_groups(records, threshold):
    total = len(records)
    parent = list(range(total))
    pair_distances = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        root_a = find(a)
        root_b = find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    comparisons = 0
    for i in range(total):
        for j in range(i + 1, total):
            comparisons += 1
            distance = hamming_distance(records[i]["dhash"], records[j]["dhash"])
            if distance <= threshold:
                union(i, j)
                pair_distances[(i, j)] = distance

    grouped_indices = {}
    for idx in range(total):
        root = find(idx)
        grouped_indices.setdefault(root, []).append(idx)

    groups = [group for group in grouped_indices.values() if len(group) > 1]
    groups.sort(key=lambda grp: min(records[i]["id"] for i in grp))

    print(f"Compared {comparisons} image pairs.")
    print(f"Found {len(groups)} visual duplicate group(s).")
    return groups, pair_distances


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def export_groups(records, groups, pair_distances, output_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = os.path.abspath(os.path.join(output_dir, f"review_{timestamp}"))
    ensure_dir(run_folder)

    report_path = os.path.join(run_folder, "duplicate_report.csv")
    rows_to_delete = []

    with open(report_path, "w", newline="", encoding="utf-8") as report_file:
        writer = csv.writer(report_file)
        writer.writerow(
            [
                "group_id",
                "db_id",
                "role",
                "filename",
                "distance_to_keeper",
                "added_date",
                "category",
                "description",
                "exported_file",
            ]
        )

        for group_no, group in enumerate(groups, start=1):
            ordered = sorted(group, key=lambda idx: records[idx]["id"])
            keeper_idx = ordered[0]
            keeper = records[keeper_idx]

            group_folder = os.path.join(run_folder, f"group_{group_no:04d}")
            ensure_dir(group_folder)

            for idx in ordered:
                record = records[idx]
                role = "KEEP" if idx == keeper_idx else "DELETE_CANDIDATE"
                if role == "DELETE_CANDIDATE":
                    rows_to_delete.append(record["id"])

                if idx == keeper_idx:
                    distance_to_keeper = 0
                else:
                    key = (keeper_idx, idx) if keeper_idx < idx else (idx, keeper_idx)
                    distance_to_keeper = pair_distances.get(
                        key, hamming_distance(keeper["dhash"], record["dhash"])
                    )

                ext = os.path.splitext(record["filename"])[1].lower()
                if ext not in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"]:
                    ext = ".jpg"

                export_filename = (
                    f"{role}__id{record['id']}__d{distance_to_keeper}__"
                    f"{sanitize_filename(record['filename'])}{ext if not record['filename'].lower().endswith(ext) else ''}"
                )
                export_path = os.path.join(group_folder, export_filename)

                with open(export_path, "wb") as out:
                    out.write(record["file_data"])

                writer.writerow(
                    [
                        group_no,
                        record["id"],
                        role,
                        record["filename"],
                        distance_to_keeper,
                        record["added_date"] or "",
                        record["xml_subject"] or "",
                        record["description"] or "",
                        export_filename,
                    ]
                )

    print(f"Exported review files to: {run_folder}")
    print(f"Report written to: {report_path}")
    print(f"Total delete candidates: {len(rows_to_delete)}")
    return run_folder, sorted(rows_to_delete)


def delete_candidates(conn, row_ids):
    if not row_ids:
        print("No rows to delete.")
        return

    print(f"\nDelete candidates: {len(row_ids)} row(s)")
    print("Type DELETE to confirm database deletion.")
    confirmation = input("> ").strip()
    if confirmation != "DELETE":
        print("Deletion cancelled.")
        return

    cursor = conn.cursor()
    for row_id in row_ids:
        cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id = ?", (row_id,))
    conn.commit()
    print(f"Deleted {len(row_ids)} duplicate row(s) from database.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Find visual duplicates in image_comp, export groups for review, and optionally delete."
    )
    parser.add_argument(
        "--distance-threshold",
        type=int,
        default=DEFAULT_DISTANCE_THRESHOLD,
        help=f"Max Hamming distance for visual duplicates (default: {DEFAULT_DISTANCE_THRESHOLD}).",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Base output folder for duplicate review exports (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="After export/review prompt, allow deleting duplicate candidates from DB.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.distance_threshold < 0:
        print("ERROR: --distance-threshold must be >= 0.")
        sys.exit(1)

    conn = connect_to_db()
    cursor = conn.cursor()

    records = load_records(cursor)
    if len(records) < 2:
        print("Not enough images to compare.")
        conn.close()
        return

    groups, pair_distances = find_groups(records, args.distance_threshold)
    if not groups:
        print("No visual duplicates found.")
        conn.close()
        return

    _, row_ids = export_groups(records, groups, pair_distances, args.output_dir)
    if args.delete:
        delete_candidates(conn, row_ids)
    else:
        print("\nNo deletion performed. Re-run with --delete after you review exported groups.")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
