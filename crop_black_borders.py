#!/usr/bin/env python3
"""Crop near-black borders from images in a folder.

Usage:
    python crop_black_borders.py "D:/Youtube/TTT/2026/06/20260601-23h/selected_images/clean" --threshold 16 --pad 2

This script finds the bounding box of pixels above the threshold (non-black), crops to that box with a small padding, and overwrites or saves to an output folder.
"""
from pathlib import Path
import argparse
import cv2
import numpy as np
import shutil


def crop_black_border(image_path: Path, out_path: Path, threshold: int = 16, pad: int = 2):
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return False
    # If image has alpha, use alpha to find content
    if img.shape[2] == 4:
        alpha = img[:, :, 3]
        mask = alpha > 0
    else:
        # convert to grayscale and threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = gray > threshold
    coords = np.column_stack(np.where(mask))
    if coords.size == 0:
        # nothing above threshold; skip
        shutil.copy2(image_path, out_path)
        return True
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    # pad and clamp
    y0 = max(0, y0 - pad)
    x0 = max(0, x0 - pad)
    y1 = min(img.shape[0] - 1, y1 + pad)
    x1 = min(img.shape[1] - 1, x1 + pad)

    cropped = img[y0:y1+1, x0:x1+1]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), cropped)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path, help='Folder with images to trim')
    parser.add_argument('--threshold', type=int, default=16)
    parser.add_argument('--pad', type=int, default=2)
    parser.add_argument('--inplace', action='store_true', help='Overwrite originals')
    args = parser.parse_args()

    folder = args.folder
    if not folder.exists() or not folder.is_dir():
        print('Folder not found:', folder)
        return
    out_folder = folder if args.inplace else folder.parent / (folder.name + '_trim')
    if out_folder.exists() and not args.inplace:
        shutil.rmtree(out_folder)
    out_folder.mkdir(parents=True, exist_ok=True)

    images = sorted([p for p in folder.iterdir() if p.suffix.lower() in ('.png', '.jpg', '.jpeg')])
    print(f'Found {len(images)} images in {folder}, saving to {out_folder}')
    for p in images:
        print('  Crop', p.name)
        crop_black_border(p, out_folder / p.name, threshold=args.threshold, pad=args.pad)

if __name__ == '__main__':
    main()
