import argparse
from collections import deque
from pathlib import Path

import cv2
import numpy as np

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _normalize_profile(values: np.ndarray) -> np.ndarray:
    """Robustly normalize a 1D float profile to [0, 1]."""
    low = float(np.percentile(values, 5))
    high = float(np.percentile(values, 95))
    if high <= low + 1e-6:
        return np.zeros_like(values, dtype=np.float32)
    out = (values - low) / (high - low)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _detect_panel_range_from_profile(
    score: np.ndarray,
    low_frac: float,
    high_frac: float,
    min_frac: float,
    expand_frac: float,
) -> tuple[int, int] | None:
    """Detect a center run in a 1D profile using gradient edges."""
    length = len(score)
    if length < 16:
        return None

    edge_band = max(2, int(length * 0.12))
    side_mean = float(np.mean(np.concatenate([score[:edge_band], score[length - edge_band :]])))
    center_band = max(4, int(length * 0.18))
    c0 = max(0, length // 2 - center_band // 2)
    c1 = min(length, c0 + center_band)
    center_mean = float(np.mean(score[c0:c1]))
    if center_mean <= side_mean + 0.08:
        return None

    grad = np.gradient(score).astype(np.float32)
    grad = cv2.GaussianBlur(grad.reshape(1, -1), (0, 0), sigmaX=3.0).reshape(-1)

    s0 = max(1, int(length * low_frac))
    s1 = max(s0 + 1, int(length * high_frac))
    e0 = min(length - 2, int(length * (1.0 - high_frac)))
    e1 = max(e0 + 1, int(length * (1.0 - low_frac)))

    left_slice = grad[s0:s1]
    right_slice = grad[e0:e1]
    if left_slice.size == 0 or right_slice.size == 0:
        return None

    start = s0 + int(np.argmax(left_slice))
    end = e0 + int(np.argmin(right_slice))
    if end <= start:
        return None

    inner_mean = float(np.mean(score[start : end + 1]))
    outer_parts = []
    if start > 0:
        outer_parts.append(score[:start])
    if end + 1 < length:
        outer_parts.append(score[end + 1 :])
    outer_mean = float(np.mean(np.concatenate(outer_parts))) if outer_parts else side_mean
    if inner_mean <= outer_mean + 0.05:
        return None

    pad = max(1, int(length * expand_frac))
    start = max(0, start - pad)
    end = min(length - 1, end + pad)

    if end - start + 1 < int(length * min_frac):
        return None

    return start, end


def _axis_panel_score(image_bgr: np.ndarray, axis: int) -> np.ndarray:
    """Build a 1D center-panel score along columns (axis=0) or rows (axis=1)."""
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = image_bgr.shape[:2]

    if axis == 0:
        side_n = max(4, int(w * 0.1))
        ref_a = np.median(lab[:, :side_n, :].reshape(-1, 3), axis=0)
        ref_b = np.median(lab[:, w - side_n :, :].reshape(-1, 3), axis=0)
        d_a = np.linalg.norm(lab - ref_a[None, None, :], axis=2)
        d_b = np.linalg.norm(lab - ref_b[None, None, :], axis=2)
        dist_score = np.mean(np.minimum(d_a, d_b), axis=0).astype(np.float32)
        lightness = np.mean(lab[:, :, 0], axis=0).astype(np.float32)
        edge = np.mean(np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)), axis=0).astype(np.float32)
    else:
        side_n = max(4, int(h * 0.1))
        ref_a = np.median(lab[:side_n, :, :].reshape(-1, 3), axis=0)
        ref_b = np.median(lab[h - side_n :, :, :].reshape(-1, 3), axis=0)
        d_a = np.linalg.norm(lab - ref_a[None, None, :], axis=2)
        d_b = np.linalg.norm(lab - ref_b[None, None, :], axis=2)
        dist_score = np.mean(np.minimum(d_a, d_b), axis=1).astype(np.float32)
        lightness = np.mean(lab[:, :, 0], axis=1).astype(np.float32)
        edge = np.mean(np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)), axis=1).astype(np.float32)

    score = (
        0.55 * _normalize_profile(dist_score)
        + 0.25 * _normalize_profile(lightness)
        + 0.20 * _normalize_profile(edge)
    ).astype(np.float32)
    return cv2.GaussianBlur(score.reshape(1, -1), (0, 0), sigmaX=6.0).reshape(-1)


def central_grayscale_foreground_mask(
    image_bgr: np.ndarray,
    gray_tolerance: int = 24,
) -> np.ndarray:
    """Detect the central grayscale photo region and return a foreground mask."""
    h, w = image_bgr.shape[:2]

    # For grayscale-like pixels, channels are close to each other.
    max_c = np.max(image_bgr, axis=2).astype(np.int16)
    min_c = np.min(image_bgr, axis=2).astype(np.int16)
    chroma = max_c - min_c
    gray_like = chroma <= gray_tolerance

    # Keep only connected components that touch the center window.
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        gray_like.astype(np.uint8),
        connectivity=8,
    )
    if num_labels <= 1:
        return np.zeros((h, w), dtype=np.uint8)

    cy0, cy1 = int(h * 0.2), int(h * 0.8)
    cx0, cx1 = int(w * 0.3), int(w * 0.7)
    center_window = labels[cy0:cy1, cx0:cx1]
    center_labels = set(np.unique(center_window).tolist())
    center_labels.discard(0)

    mask = np.zeros((h, w), dtype=np.uint8)
    for label in center_labels:
        area = stats[label, cv2.CC_STAT_AREA]
        if area < (h * w * 0.02):
            continue
        mask[labels == label] = 255

    # Fill small gaps and smooth edges.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask


def detect_center_panel_bounds(image_bgr: np.ndarray) -> tuple[int, int] | None:
    """Detect left/right bounds of the central photo panel.

    This is intentionally conservative: if detection is uncertain, return None.
    """
    h, w = image_bgr.shape[:2]
    if w < 32:
        return None

    x_score = _axis_panel_score(image_bgr, axis=0)
    bounds = _detect_panel_range_from_profile(
        x_score,
        low_frac=0.08,
        high_frac=0.48,
        min_frac=0.2,
        expand_frac=0.006,
    )
    if bounds is None:
        return None
    left, right = bounds
    panel_w = right - left + 1
    if panel_w > int(w * 0.96):
        return None
    return bounds


def detect_center_panel_rectangle(image_bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    """Detect a full center panel rectangle (left, right, top, bottom)."""
    h, w = image_bgr.shape[:2]
    x_bounds = detect_center_panel_bounds(image_bgr)
    if x_bounds is None:
        return None

    left, right = x_bounds
    panel = image_bgr[:, left : right + 1]
    y_score = _axis_panel_score(panel, axis=1)
    y_bounds = _detect_panel_range_from_profile(
        y_score,
        low_frac=0.05,
        high_frac=0.45,
        min_frac=0.15,
        expand_frac=0.006,
    )
    if y_bounds is None:
        return left, right, 0, h - 1

    top, bottom = y_bounds
    if bottom - top + 1 > int(h * 0.97):
        top, bottom = 0, h - 1
    return left, right, top, bottom


def center_panel_foreground_mask(image_bgr: np.ndarray) -> np.ndarray | None:
    """Return a full-height foreground mask for the detected center panel."""
    h, w = image_bgr.shape[:2]
    bounds = detect_center_panel_bounds(image_bgr)
    if bounds is None:
        return None

    left, right = bounds
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[:, left : right + 1] = 255
    return mask


def _center_run(flags: np.ndarray, center_idx: int) -> tuple[int, int] | None:
    """Return contiguous True run containing center_idx, or None if center is False."""
    if center_idx < 0 or center_idx >= len(flags) or not flags[center_idx]:
        return None

    lo = center_idx
    while lo > 0 and flags[lo - 1]:
        lo -= 1
    hi = center_idx
    while hi < len(flags) - 1 and flags[hi + 1]:
        hi += 1
    return lo, hi


def enforce_solid_center_rectangle(mask: np.ndarray) -> np.ndarray:
    """Force a hole-free center rectangle from an existing mask (both axes)."""
    h, w = mask.shape[:2]
    col_cov = np.mean(mask > 0, axis=0)
    cols = col_cov > 0.03
    row_cov = np.mean(mask > 0, axis=1)
    rows = row_cov > 0.03

    x_run = _center_run(cols, w // 2)
    y_run = _center_run(rows, h // 2)
    if x_run is None or y_run is None:
        return mask

    left, right = x_run
    top, bottom = y_run

    if right - left + 1 < int(w * 0.15):
        return mask
    if bottom - top + 1 < int(h * 0.15):
        return mask

    out = np.zeros((h, w), dtype=np.uint8)
    out[top : bottom + 1, left : right + 1] = 255
    return out


def color_distance_lab(image_bgr: np.ndarray, ref_bgr: np.ndarray) -> np.ndarray:
    """Return per-pixel Euclidean distance in LAB color space from reference color."""
    img_lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    ref_pixel = np.array([[ref_bgr]], dtype=np.uint8)
    ref_lab = cv2.cvtColor(ref_pixel, cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0]
    return np.linalg.norm(img_lab - ref_lab, axis=2)


def estimate_background_color(image_bgr: np.ndarray, border_ratio: float = 0.08) -> np.ndarray:
    """Estimate background color using pixels from the outer border region."""
    h, w = image_bgr.shape[:2]
    b = max(1, int(min(h, w) * border_ratio))

    top = image_bgr[:b, :, :].reshape(-1, 3)
    bottom = image_bgr[h - b :, :, :].reshape(-1, 3)
    left = image_bgr[:, :b, :].reshape(-1, 3)
    right = image_bgr[:, w - b :, :].reshape(-1, 3)

    border_pixels = np.vstack([top, bottom, left, right])
    return np.median(border_pixels, axis=0).astype(np.uint8)


def border_connected_background_mask(
    image_bgr: np.ndarray,
    threshold: float,
    border_ratio: float = 0.08,
) -> np.ndarray:
    """Find background pixels connected to the image border with similar color."""
    h, w = image_bgr.shape[:2]
    bg_color = estimate_background_color(image_bgr, border_ratio=border_ratio)
    dist = color_distance_lab(image_bgr, bg_color)
    candidate = dist <= threshold

    visited = np.zeros((h, w), dtype=bool)
    background = np.zeros((h, w), dtype=bool)
    q = deque()

    for x in range(w):
        if candidate[0, x]:
            q.append((0, x))
            visited[0, x] = True
        if candidate[h - 1, x] and not visited[h - 1, x]:
            q.append((h - 1, x))
            visited[h - 1, x] = True

    for y in range(h):
        if candidate[y, 0] and not visited[y, 0]:
            q.append((y, 0))
            visited[y, 0] = True
        if candidate[y, w - 1] and not visited[y, w - 1]:
            q.append((y, w - 1))
            visited[y, w - 1] = True

    while q:
        y, x = q.popleft()
        background[y, x] = True

        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and candidate[ny, nx]:
                visited[ny, nx] = True
                q.append((ny, nx))

    return background


def remove_background_to_alpha(
    image_bgr: np.ndarray,
    threshold: float = 17.0,
    blur_edges: bool = True,
) -> np.ndarray:
    """Remove side/background area and return BGRA image with transparent background."""
    # 1) Prefer robust center-panel detection so center content is never carved out.
    fg_mask = center_panel_foreground_mask(image_bgr)

    # 2) If panel detection fails, try grayscale-region detection.
    if fg_mask is None:
        fg_mask = central_grayscale_foreground_mask(image_bgr)

    # 3) If still suspicious, fallback to border-color segmentation.
    coverage = float(np.count_nonzero(fg_mask)) / float(fg_mask.size)
    if coverage < 0.12 or coverage > 0.98:
        mask_bg = border_connected_background_mask(image_bgr, threshold=threshold)
        fg_mask = (~mask_bg).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)

    # Safety: keep a solid rectangular center panel to avoid deleting center content.
    fg_mask = enforce_solid_center_rectangle(fg_mask)

    if blur_edges:
        fg_mask = cv2.GaussianBlur(fg_mask, (0, 0), sigmaX=1.0, sigmaY=1.0)

    b, g, r = cv2.split(image_bgr)
    return cv2.merge((b, g, r, fg_mask))


def crop_to_foreground_panel(
    image_bgr: np.ndarray,
    threshold: float = 17.0,
    pad_x_ratio: float = 0.01,
    pad_y_ratio: float = 0.0,
    inset_x_ratio: float = 0.012,
    inset_y_ratio: float = 0.0,
    crop_vertical: bool = False,
) -> np.ndarray:
    """Crop image to the detected foreground panel rectangle."""
    rect = detect_center_panel_rectangle(image_bgr)
    if rect is None:
        alpha_img = remove_background_to_alpha(image_bgr, threshold=threshold, blur_edges=False)
        alpha = alpha_img[:, :, 3]
        ys, xs = np.where(alpha > 20)
        if len(xs) == 0:
            return image_bgr
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
    else:
        x0, x1, y0, y1 = rect

    h, w = image_bgr.shape[:2]
    px = max(1, int(w * pad_x_ratio))
    py = max(0, int(h * pad_y_ratio))
    ix = max(0, int(w * inset_x_ratio))
    iy = max(0, int(h * inset_y_ratio))

    x0 = max(0, x0 - px)
    x1 = min(w - 1, x1 + px)
    if crop_vertical:
        y0 = max(0, y0 - py)
        y1 = min(h - 1, y1 + py)
    else:
        y0 = 0
        y1 = h - 1

    if x1 - x0 + 1 > 2 * ix + 8:
        x0 += ix
        x1 -= ix
    if crop_vertical and y1 - y0 + 1 > 2 * iy + 8:
        y0 += iy
        y1 -= iy

    return image_bgr[y0 : y1 + 1, x0 : x1 + 1]


def is_original_image(path: Path) -> bool:
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        return False
    lower_name = path.stem.lower()
    return not lower_name.endswith("-corrected")


def output_name_for(path: Path) -> str:
    return f"{path.stem}.png"


def process_folder(
    input_dir: Path,
    output_dir: Path,
    threshold: float,
    mode: str,
    crop_padding_x_ratio: float,
    crop_padding_y_ratio: float,
    crop_inset_x_ratio: float,
    crop_inset_y_ratio: float,
    crop_vertical: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    all_files = sorted([p for p in input_dir.iterdir() if p.is_file()])
    files = [p for p in all_files if is_original_image(p)]
    skipped_non_images = [
        p for p in all_files if p.suffix.lower() not in IMAGE_SUFFIXES and not p.stem.lower().endswith("-corrected")
    ]

    if not files:
        print("No source images found. Source files must not end with '-corrected'.")
        return

    if skipped_non_images:
        print(f"[INFO] Skipping {len(skipped_non_images)} non-image files.")
        preview = skipped_non_images[:8]
        for p in preview:
            print(f"[INFO] Non-image skipped: {p.name}")
        if len(skipped_non_images) > len(preview):
            print(f"[INFO] ... and {len(skipped_non_images) - len(preview)} more non-image files.")

    ok = 0
    for src in files:
        img = cv2.imread(str(src), cv2.IMREAD_COLOR)
        if img is None:
            print(f"[SKIP] Cannot read: {src}")
            continue

        if mode == "crop":
            out = crop_to_foreground_panel(
                img,
                threshold=threshold,
                pad_x_ratio=crop_padding_x_ratio,
                pad_y_ratio=crop_padding_y_ratio,
                inset_x_ratio=crop_inset_x_ratio,
                inset_y_ratio=crop_inset_y_ratio,
                crop_vertical=crop_vertical,
            )
        else:
            out = remove_background_to_alpha(img, threshold=threshold)
        dst = output_dir / output_name_for(src)

        if cv2.imwrite(str(dst), out):
            ok += 1
            print(f"[OK] {src.name} -> {dst.name}")
        else:
            print(f"[FAIL] Could not write: {dst}")

    print(f"Done. Processed {ok}/{len(files)} images.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-remove uniform border background and export transparent PNG files.",
    )
    parser.add_argument("input_folder", help="Folder with source images.")
    parser.add_argument("output_folder", help="Folder where corrected images are saved.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=17.0,
        help="Color-distance threshold in LAB space (default: 17.0). Increase for more aggressive removal.",
    )
    parser.add_argument(
        "--mode",
        choices=["alpha", "crop"],
        default="alpha",
        help="Output mode: 'alpha' keeps original size with transparency, 'crop' trims to the center panel rectangle.",
    )
    parser.add_argument(
        "--crop-padding-x-ratio",
        type=float,
        default=0.01,
        help="Extra horizontal padding around detected crop box in crop mode (default: 0.01).",
    )
    parser.add_argument(
        "--crop-padding-y-ratio",
        type=float,
        default=0.0,
        help="Extra vertical padding around detected crop box in crop mode (default: 0.0). Only used with --crop-vertical.",
    )
    parser.add_argument(
        "--crop-inset-x-ratio",
        type=float,
        default=0.012,
        help="Trim slightly inside the detected crop box horizontally to remove residual frame (default: 0.012).",
    )
    parser.add_argument(
        "--crop-inset-y-ratio",
        type=float,
        default=0.0,
        help="Trim slightly inside the detected crop box vertically (default: 0.0). Only used with --crop-vertical.",
    )
    parser.add_argument(
        "--crop-vertical",
        action="store_true",
        help="Also crop vertically. Disabled by default to avoid losing top/bottom image content.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_dir = Path(args.input_folder)
    output_dir = Path(args.output_folder)

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input folder does not exist or is not a folder: {input_dir}")

    process_folder(
        input_dir=input_dir,
        output_dir=output_dir,
        threshold=args.threshold,
        mode=args.mode,
        crop_padding_x_ratio=max(0.0, float(args.crop_padding_x_ratio)),
        crop_padding_y_ratio=max(0.0, float(args.crop_padding_y_ratio)),
        crop_inset_x_ratio=max(0.0, float(args.crop_inset_x_ratio)),
        crop_inset_y_ratio=max(0.0, float(args.crop_inset_y_ratio)),
        crop_vertical=bool(args.crop_vertical),
    )


if __name__ == "__main__":
    main()
