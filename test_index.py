import sqlite3
import cv2
import numpy as np
import hashlib
from collections import defaultdict

DB_NAME = "image_collection.db"
DB_TABLE_NAME = "image_comp"
VISUAL_DUPLICATE_DISTANCE_THRESHOLD = 6

def decode_blob_to_image(file_data):
    np_data = np.frombuffer(file_data, dtype=np.uint8)
    return cv2.imdecode(np_data, cv2.IMREAD_COLOR)

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
    if img is None or img.size == 0:
        return ""
    return hashlib.sha256(img.tobytes() + str(img.shape).encode("utf-8")).hexdigest()

def compute_ahash_from_image(img, hash_size=8):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    avg = resized.mean()
    diff = resized >= avg
    bits = "".join("1" if v else "0" for v in diff.flatten())
    return format(int(bits, 2), "016x")

def build_duplicate_index_from_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"SELECT id, filename, file_data FROM {DB_TABLE_NAME} LIMIT 10")
    rows = cursor.fetchall()
    conn.close()

    loaded = 0
    failed = 0
    
    for row_id, filename, file_data in rows:
        if not file_data:
            print(f"  Row {row_id}: no file_data")
            failed += 1
            continue
        img = decode_blob_to_image(file_data)
        if img is None:
            print(f"  Row {row_id}: failed to decode image")
            failed += 1
            continue
        print(f"  Row {row_id}: {filename} - decoded OK (shape={img.shape})")
        loaded += 1
    
    print(f"\nLoaded: {loaded}, Failed: {failed}")

print(f"Checking first 10 rows in {DB_TABLE_NAME}:")
build_duplicate_index_from_db()
