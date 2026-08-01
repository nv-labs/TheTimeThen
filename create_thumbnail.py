from pathlib import Path
import argparse
import random
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}


def crop_black_borders(img: Image.Image, threshold: int = 16):
    """Aggressively crop dark borders using multiple passes to remove wavy edges."""
    import cv2
    
    arr = np.asarray(img.convert('RGB'))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    
    # Multiple thresholding passes to catch all dark areas
    for t in [threshold, threshold + 8]:
        _, mask = cv2.threshold(gray, t, 255, cv2.THRESH_BINARY)
        
        # Remove noise and small objects
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        coords = np.argwhere(mask)
        if coords.size > 100:  # Ensure we have content
            y0, x0 = coords.min(axis=0)
            y1, x1 = coords.max(axis=0) + 1
            # Add small inset to remove remaining fuzzy edges
            inset = 2
            x0, y0 = max(0, x0 + inset), max(0, y0 + inset)
            x1, y1 = min(arr.shape[1], x1 - inset), min(arr.shape[0], y1 - inset)
            if x1 > x0 and y1 > y0:
                return img.crop((x0, y0, x1, y1))
    
    return img


def resize_and_crop(img, target_height, target_width):
    """Resize image to fit target dimensions with center crop, preserving quality."""
    aspect = img.width / img.height
    target_aspect = target_width / target_height

    if aspect > target_aspect:
        # Image is wider than target
        new_height = target_height
        new_width = int(aspect * new_height)
    else:
        # Image is taller than target
        new_width = target_width
        new_height = int(new_width / aspect)

    # Use LANCZOS for high-quality downsampling
    img = img.resize((new_width, new_height), Image.LANCZOS)
    
    # Center crop to exact dimensions
    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2
    right = left + target_width
    bottom = top + target_height
    return img.crop((left, top, right, bottom))


def trim_bottom_caption_region(img: Image.Image, trim_ratio: float = 0.14) -> Image.Image:
    """Trim a portion of the bottom where source captions/subtitles usually appear."""
    if trim_ratio <= 0:
        return img
    trim_pixels = int(img.height * trim_ratio)
    if trim_pixels <= 0 or trim_pixels >= img.height - 1:
        return img
    return img.crop((0, 0, img.width, img.height - trim_pixels))


def load_font(size: int):
    possible_fonts = [
        'arial.ttf',
        'Arial.ttf',
        'DejaVuSans-Bold.ttf',
        'DejaVuSans.ttf',
    ]
    for font_name in possible_fonts:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def get_text_bbox(draw, text: str, font):
    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    return None


def _folder_has_images(folder: Path, min_count: int = 2) -> bool:
    if not folder.is_dir():
        return False
    images = [p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    return len(images) >= min_count


def find_selected_images_root(folder: Path) -> Path | None:
    candidate = folder / 'selected_images'
    if candidate.is_dir():
        return candidate
    for selected in folder.rglob('selected_images'):
        if selected.is_dir():
            return selected
    return None


def find_image_folder(folder: Path) -> Path:
    candidates = [
        folder / 'selected_images' / 'clean',
        folder / 'selected_images',
        folder / 'clean',
        folder,
    ]
    for candidate in candidates:
        if _folder_has_images(candidate):
            return candidate

    for selected in folder.rglob('selected_images'):
        clean_candidate = selected / 'clean'
        if _folder_has_images(clean_candidate):
            return clean_candidate
    for selected in folder.rglob('selected_images'):
        if _folder_has_images(selected):
            return selected
    for clean in folder.rglob('clean'):
        if _folder_has_images(clean):
            return clean

    raise FileNotFoundError(f"No folder with at least 2 supported images found under {folder}. Searched: {candidates}")


def find_autos_python() -> Path:
    candidate = Path(__file__).parent.parent / 'autos' / 'Scripts' / 'python.exe'
    if candidate.exists():
        return candidate
    return Path(sys.executable)


def ensure_clean_images(folder: Path) -> Path:
    selected_root = find_selected_images_root(folder)

    if selected_root is None:
        raise FileNotFoundError(f"No selected_images folder found under {folder}")

    # Always refresh clean images so we never reuse stale clean outputs from
    # earlier runs that may still include bad intro/outro samples.
    print(f"Refreshing cleaned images in {selected_root} before thumbnail generation.")
    script = Path(__file__).parent / 'remove_text_and_bg.py'
    if not script.exists():
        raise FileNotFoundError(f"{script} not found; cannot auto-clean images")
    python_exe = find_autos_python()
    subprocess.run([str(python_exe), str(script), '--folder', str(selected_root)], check=True)

    return find_image_folder(folder)


def select_two_random_images(folder: Path):
    image_folder = ensure_clean_images(folder)
    images = [p for p in sorted(image_folder.iterdir()) if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    
    if len(images) < 2:
        raise FileNotFoundError(f"Need at least 2 images, but only found {len(images)} in {image_folder}")

    # Avoid intro/outro picks by selecting only from the in-between portion.
    # Keep a stronger exclusion on both sides to handle variable intro/outro length.
    edge_exclusion = max(1, min(len(images) // 3, int(len(images) * 0.2)))
    if len(images) >= 8:
        edge_exclusion = max(edge_exclusion, 2)
    middle_images = images[edge_exclusion:len(images) - edge_exclusion]
    if len(middle_images) < 2:
        raise FileNotFoundError(
            f"Need at least 2 in-between images after excluding {edge_exclusion} from start/end, "
            f"but only found {len(middle_images)} in {image_folder}"
        )
    
    # Ensure we select two truly different images
    max_attempts = 10
    for attempt in range(max_attempts):
        selected = random.sample(middle_images, 2)
        # Verify they are actually different files
        if selected[0].resolve() != selected[1].resolve():
            return selected[0], selected[1]
    
    # If we couldn't find 2 different images after retries, raise error
    raise ValueError(
        f"Could not select 2 different in-between images from {image_folder} after {max_attempts} attempts. "
        f"Found {len(middle_images)} in-between images but they may be duplicates or symbolic links."
    )


def create_side_by_side_thumbnail(left_image_path, right_image_path, output_path, total_width=1280, total_height=720):
    # Safety check: ensure we're not using the same image twice
    left_path = Path(left_image_path).resolve()
    right_path = Path(right_image_path).resolve()
    
    print(f"Left image:  {left_path}")
    print(f"Right image: {right_path}")
    
    if left_path == right_path:
        raise ValueError(f"ERROR: Left and right images are the same file!\n  {left_path}\nThis should never happen. Check if the image folder has duplicate files or symbolic links.")
    
    left_img = Image.open(left_image_path).convert('RGB')
    right_img = Image.open(right_image_path).convert('RGB')

    left_img = crop_black_borders(left_img, threshold=24)
    right_img = crop_black_borders(right_img, threshold=24)
    left_img = trim_bottom_caption_region(left_img, trim_ratio=0.14)
    right_img = trim_bottom_caption_region(right_img, trim_ratio=0.14)

    half_width = total_width // 2
    left_img = resize_and_crop(left_img, total_height, half_width)
    right_img = resize_and_crop(right_img, total_height, half_width)

    # Create canvas with no padding (images fill the entire space)
    combined = Image.new('RGB', (total_width, total_height))
    combined.paste(left_img, (0, 0))
    combined.paste(right_img, (half_width, 0))

    # Draw centered red dot
    draw = ImageDraw.Draw(combined)
    center_x = total_width // 2
    center_y = total_height // 2
    dot_radius = 36
    draw.ellipse(
        [(center_x - dot_radius, center_y - dot_radius),
         (center_x + dot_radius, center_y + dot_radius)],
        fill=(220, 20, 20)
    )

    # Draw "THE TIME THEN" logo at bottom-left with a solid dark band that
    # fully masks any subtitle remnants from source images.
    font = load_font(60)
    margin = 40

    background_height = 105
    overlay = Image.new('RGBA', (total_width, background_height), (0, 0, 0, 255))
    combined = combined.convert('RGBA')
    combined.paste(overlay, (0, total_height - background_height), overlay)
    combined = combined.convert('RGB')

    draw = ImageDraw.Draw(combined)

    prefix = "THE "
    highlight = "TIME"
    suffix = " THEN"
    text_bbox = get_text_bbox(draw, highlight, font)
    text_height = text_bbox[1] if text_bbox else 60
    text_y = total_height - background_height + (background_height - text_height) // 2

    x = margin
    draw.text((x, text_y), prefix, fill='white', font=font)
    x += get_text_bbox(draw, prefix, font)[0]
    draw.text((x, text_y), highlight, fill=(220, 20, 20), font=font)
    x += get_text_bbox(draw, highlight, font)[0]
    draw.text((x, text_y), suffix, fill='white', font=font)

    combined.save(output_path, quality=95)
    print(f'Thumbnail saved to {output_path}')


def main():
    parser = argparse.ArgumentParser(description='Create side-by-side thumbnail from images or a selected_images clean folder')
    parser.add_argument('--folder', type=Path, help='Folder containing selected_images/clean or clean images')
    parser.add_argument('--output', '-o', type=Path, help='Output thumbnail path')
    parser.add_argument('--width', type=int, default=1280, help='Total thumbnail width')
    parser.add_argument('--height', type=int, default=720, help='Total thumbnail height')
    parser.add_argument('left', nargs='?', help='Left image path (if not using --folder)')
    parser.add_argument('right', nargs='?', help='Right image path (if not using --folder)')
    parser.add_argument('out', nargs='?', help='Output path (if not using --folder)')
    args = parser.parse_args()

    if args.folder:
        if args.left or args.right or args.out:
            parser.error('When using --folder, do not pass positional image paths or output name.')
        if args.output:
            output_path = args.output
        else:
            output_path = args.folder / 'thumbnail.jpg'
        left_image, right_image = select_two_random_images(args.folder)
    else:
        if not args.left or not args.right or not args.out:
            parser.error('Must provide left, right, and out when not using --folder.')
        output_path = Path(args.out)
        left_image = Path(args.left)
        right_image = Path(args.right)

    create_side_by_side_thumbnail(left_image, right_image, output_path, total_width=args.width, total_height=args.height)


if __name__ == '__main__':
    main()
