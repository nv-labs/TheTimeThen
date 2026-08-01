import cv2
import numpy as np
import os
from pathlib import Path

def remove_background_smart_scan(image_path, output_path, debug_dir):
    img = cv2.imread(image_path)
    if img is None: return False
    
    h, w = img.shape[:2]
    name = os.path.basename(image_path)
    
    # 1. Convert to grayscale and calculate vertical variance
    # This detects where 'busy' detail (the photo) starts vs 'repetitive' detail (parchment)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Calculate the standard deviation of each column
    # The parchment has low variance compared to the person in the photo
    col_std = np.std(gray, axis=0)
    
    # 2. Find Left Boundary
    # Start from 5% in (to skip dark edges) and move to the middle
    left_limit = int(w * 0.4)
    start_search = int(w * 0.05)
    left = start_search
    
    # Look for a significant jump in detail
    threshold = np.mean(col_std) * 0.8 
    for i in range(start_search, left_limit):
        if col_std[i] > threshold:
            left = i
            break
            
    # 3. Find Right Boundary
    right_limit = int(w * 0.6)
    end_search = int(w * 0.95)
    right = end_search
    for i in range(end_search, right_limit, -1):
        if col_std[i] > threshold:
            right = i
            break

    # 4. Clean up the crop
    # Add a tiny buffer so we don't cut into the photo
    left = max(0, left + 5)
    right = min(w, right - 5)

    # 5. Vertical Crop (Optional - if your images have parchment top/bottom too)
    row_std = np.std(gray, axis=1)
    top = 0
    row_threshold = np.mean(row_std) * 0.7
    for i in range(int(h*0.05), int(h*0.2)):
        if row_std[i] > row_threshold:
            top = i
            break
            
    # Apply Crop
    cropped = img[top:, left:right]
    
    # Save Result
    cv2.imwrite(output_path, cropped)
    print(f"✅ Processed: {name} (Crop: L:{left} R:{right})")
    return True

def run_cleaner(input_folder, output_folder):
    in_p = Path(input_folder)
    out_p = Path(output_folder)
    debug_p = out_p / "debug"
    
    out_p.mkdir(parents=True, exist_ok=True)
    debug_p.mkdir(parents=True, exist_ok=True)
    
    for file in in_p.glob("*.*"):
        if file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            remove_background_smart_scan(str(file), str(out_p / file.name), str(debug_p))

if __name__ == "__main__":
    # Using 'r' to prevent the \D errors you had
    INPUT = r"D:\Dev\TheTimeThen\output"
    OUTPUT = r"D:\Dev\TheTimeThen\output-Clean"
    run_cleaner(INPUT, OUTPUT)