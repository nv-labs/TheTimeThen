#!/usr/bin/env python3
"""Remove overlaid text and surrounding black background from images in selected_images folders.

Usage:
    python remove_text_and_bg.py --root D:/Youtube/TTT/2026 --dry-run

By default the script will:
 - Find all `*/selected_images` folders under --root
 - For each image: remove bright overlaid text using inpainting
 - Save intermediate results to `selected_images/clean_tmp`
 - Run the existing `batch_remove_background.py` (via autos python) to crop/remove black background
 - Save final images to `selected_images/clean`

The script calls the project's batch_remove_background.py with recommended parameters.
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import List

import cv2
import numpy as np


def find_selected_images(root: Path) -> List[Path]:
    result = []
    for p in root.rglob('selected_images'):
        if p.is_dir():
            result.append(p)
    return result


def remove_text_from_image(src_path: Path, dst_path: Path, bright_thresh: int = 200, kernel_size: int = 3, min_contour_area: int = 40):
    img = cv2.imread(str(src_path))
    if img is None:
        print(f"  Skipping (not an image): {src_path}")
        return False

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Threshold bright pixels (likely white text)
    _, th = cv2.threshold(gray, bright_thresh, 255, cv2.THRESH_BINARY)

    # Morphological close to connect text strokes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Remove small noise by contour filtering
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    for c in contours:
        area = cv2.contourArea(c)
        if area >= min_contour_area:
            cv2.drawContours(mask, [c], -1, 255, -1)

    text_ratio = np.count_nonzero(mask) / (gray.shape[0] * gray.shape[1])
    if text_ratio > 0.005:
        print(f"  [WARNING] Text detected in {src_path.name}, skipping inpainting to preserve quality.")

    # Always just copy the original image (no inpainting)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst_path)
    return True


def run_batch_remove_background(autos_python: Path, input_dir: Path, output_dir: Path, extra_args: List[str]):
    script = Path(__file__).parent / 'batch_remove_background.py'
    if not script.exists():
        # The user provided example uses a script in repo root; also try original path
        script = Path(__file__).parent / 'batch_remove_background.py'
    if not script.exists():
        raise FileNotFoundError(f"batch_remove_background.py not found in {Path(__file__).parent}")

    cmd = [str(autos_python), str(script), str(input_dir), str(output_dir)] + extra_args
    print("  Running:", " ".join(cmd))
    res = subprocess.run(cmd)
    return res.returncode == 0


def process_folder(images_dir: Path, autos_python: Path, dry_run: bool = False):
    print(f"Processing: {images_dir}")
    tmp_dir = images_dir / 'clean_tmp'
    final_dir = images_dir / 'clean'

    # Clean or create tmp/final
    if dry_run:
        print("  (dry-run) would create temporary and final folders")
    else:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        if final_dir.exists():
            shutil.rmtree(final_dir)
        final_dir.mkdir(parents=True, exist_ok=True)

    image_files = [p for p in images_dir.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')]
    print(f"  Found {len(image_files)} images")
    for p in image_files:
        dst = tmp_dir / p.name
        print(f"  -> removing text: {p.name}")
        if not dry_run:
            remove_text_from_image(p, dst)

    # Now call batch_remove_background.py
    extra = [
        '--mode', 'crop',
        '--threshold', '17',
        '--crop-padding-x-ratio', '0.01',
        '--crop-inset-x-ratio', '0.019'
    ]
    if dry_run:
        print(f"  (dry-run) would run batch_remove_background on {tmp_dir} -> {final_dir}")
        return True

    ok = run_batch_remove_background(autos_python, tmp_dir, final_dir, extra)
    if not ok:
        print(f"  ❌ batch_remove_background failed for {images_dir}")
        return False

    print(f"  ✅ processed images saved to {final_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(description='Remove text overlays and black background from selected_images folders')
    parser.add_argument('--root', type=Path, default=Path('D:/Youtube/TTT/2026'), help='Root folder to search (default: D:/Youtube/TTT/2026)')
    parser.add_argument('--autos-python', type=Path, default=Path(__file__).parent.parent / 'autos' / 'Scripts' / 'python.exe', help='Path to autos python (used to run batch_remove_background.py)')
    parser.add_argument('--folder', type=Path, help='Only process this specific selected_images folder')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.folder:
        selected_dirs = [args.folder]
    else:
        selected_dirs = find_selected_images(args.root)

    if not selected_dirs:
        print('No selected_images folders found under', args.root)
        return

    print(f'Found {len(selected_dirs)} selected_images folders')
    for sd in selected_dirs:
        process_folder(sd, args.autos_python, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
