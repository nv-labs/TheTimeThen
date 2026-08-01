import sqlite3
import os
import random
import shutil

def count_images_and_export_random(db_path, table_name, output_folder, num_images=50):
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.heic'}

    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count the total number of images
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    total_images = cursor.fetchone()[0]
    print(f"Total images in the database: {total_images}")

    # Fetch candidate media paths with row id for unique export names
    cursor.execute(
        f"SELECT id, source_path FROM {table_name} "
        "WHERE source_path IS NOT NULL AND source_path != ''"
    )
    rows = cursor.fetchall()

    # Keep only existing local files
    valid_rows = [
        (row_id, source_path)
        for row_id, source_path in rows
        if os.path.exists(source_path) and os.path.splitext(source_path)[1].lower() in image_extensions
    ]

    # Ensure the output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Clear previous exported files so each run reflects only the current random sample
    for existing_name in os.listdir(output_folder):
        existing_path = os.path.join(output_folder, existing_name)
        if os.path.isfile(existing_path):
            os.remove(existing_path)

    # Select random images
    if len(valid_rows) == 0:
        print("No valid images found in the database.")
        conn.close()
        return

    selected_rows = random.sample(valid_rows, min(num_images, len(valid_rows)))

    # Log selected images for debugging
    print("Selected images:")
    for row_id, img in selected_rows:
        print(f"{row_id}: {img}")

    # Copy selected images to the output folder
    copied_count = 0
    for row_id, image_path in selected_rows:
        if os.path.exists(image_path):
            base_name = os.path.basename(image_path)
            destination = os.path.join(output_folder, f"{row_id}_{base_name}")
            shutil.copy2(image_path, destination)
            copied_count += 1
        else:
            print(f"Warning: Image file not found: {image_path}")

    print(f"Exported {copied_count} images to {output_folder}")

    # Close the database connection
    conn.close()

if __name__ == "__main__":
    db_path = "d:/Dev/TheTimeThen/google_takeout_photos_2023.db"
    table_name = "photos"
    output_folder = "d:/Dev/TheTimeThen/exported_images"

    count_images_and_export_random(db_path, table_name, output_folder)