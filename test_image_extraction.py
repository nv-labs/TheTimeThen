"""
Quick test: run crop_center_photo + text extraction on 3 real images,
produce output images and a text file exactly like the pipeline does.

For debug_table_dump images, prefer sidecar .txt captions (00001.txt, ...)
because these static photos do not contain readable bottom caption overlays.
"""

import os
import sys
import cv2

sys.path.insert(0, os.path.dirname(__file__))
import auto_extract_centered_historical_photos as m

TEST_IMAGES = [
    r"D:\Dev\TheTimeThen\debug_table_dump\00001.jpg",
    r"D:\Dev\TheTimeThen\debug_table_dump\00002.jpg",
    r"D:\Dev\TheTimeThen\debug_table_dump\00003.jpg",
]
OUTPUT_DIR = r"D:\Dev\TheTimeThen\output_test"
TEXT_FILE = os.path.join(OUTPUT_DIR, "centered_extracted_text.txt")


def load_sidecar_caption(image_path):
    txt_path = os.path.splitext(image_path)[0] + ".txt"
    if not os.path.exists(txt_path):
        return ""

    caption_lines = []
    with open(txt_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("ID:") or line.startswith("Filename:"):
                continue
            caption_lines.append(line)

    return " ".join(caption_lines).strip()


os.makedirs(OUTPUT_DIR, exist_ok=True)
if os.path.exists(TEXT_FILE):
    os.remove(TEXT_FILE)

print(f"Output folder : {OUTPUT_DIR}")
print(f"Text file     : {TEXT_FILE}")
print()

for idx, img_path in enumerate(TEST_IMAGES, start=1):
    if not os.path.exists(img_path):
        print(f"[SKIP] image not found: {img_path}")
        continue

    img = cv2.imread(img_path)
    if img is None:
        print(f"[SKIP] cannot read: {img_path}")
        continue

    text = load_sidecar_caption(img_path)
    text_source = "sidecar"
    if not text:
        text = m.ocr_caption(img)
        text_source = "ocr"

    cropped = m.crop_center_photo(img)

    summary = m.summarize_text(text, max_words=4) if text else "image"
    out_name = f"{summary}--{idx}.png"
    out_path = os.path.join(OUTPUT_DIR, out_name)

    cv2.imwrite(out_path, cropped)

    with open(TEXT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{idx} | {text}\n")

    print(f"[OK] #{idx}  {os.path.basename(img_path)}")
    print(f"   source : {text_source}")
    print(f"   text   : {text[:120] if text else '(empty)'}")
    print(f"   input  : {img.shape[1]}x{img.shape[0]} px")
    print(f"   output : {cropped.shape[1]}x{cropped.shape[0]} px  -> {out_name}")
    print()

print("-- Text file contents ------------------------------------------")
if os.path.exists(TEXT_FILE):
    with open(TEXT_FILE, encoding="utf-8") as f:
        print(f.read())
else:
    print("(no text file created)")

print("Done.")
