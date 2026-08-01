import sqlite3
import os
from PIL import Image, ImageDraw, ImageFont
import io
import sys
import numpy as np
import imageio
import textwrap
import random
from datetime import datetime
import ffmpeg  # Import ffmpeg-python for audio merging

def create_image_db(db_name='universal_image_archive.db'):
    """Creates or updates a database for storing files and metadata."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS archived_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            file_size INTEGER,
            file_data BLOB NOT NULL,
            source_url TEXT NOT NULL UNIQUE,
            file_type TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("PRAGMA table_info(archived_files)")
    columns = [info[1] for info in cursor.fetchall()]
    
    new_columns = [
        ('xml_collection', 'TEXT'),
        ('xml_date', 'TEXT'),
        ('xml_subject', 'TEXT'),
        ('xml_language', 'TEXT'),
        ('xml_title', 'TEXT'),
        ('description', 'TEXT'),
        ('VideoAirDate', 'TEXT')
    ]
    
    for column_name, column_type in new_columns:
        if column_name not in columns:
            cursor.execute(f'ALTER TABLE archived_files ADD COLUMN {column_name} {column_type}')
    
    conn.commit()
    return conn

def add_stars(bg_img, num_stars=200):
    """Add random white stars to the background image."""
    w, h = bg_img.size
    draw = ImageDraw.Draw(bg_img)
    for _ in range(num_stars):
        x = random.randint(0, w)
        y = random.randint(0, h)
        size = random.randint(1, 2)
        draw.ellipse((x - size, y - size, x + size, y + size), fill=(255, 255, 255))

def main():
    DATABASE_NAME = 'universal_image_archive.db'
    AUDIO_FILE = r"D:\Dev\automation\VideoAssets\Andres Jacque - Skipping [Thematic].mp3"  # Path to audio file
    
    # No command-line arguments needed
    if len(sys.argv) > 1:
        print("No arguments needed. Usage: python vidCreate.py")
        sys.exit(1)
    
    conn = None
    
    try:
        conn = create_image_db(DATABASE_NAME)
        cursor = conn.cursor()
        
        # Create video from the last 35 images added to the DB
        print("Creating video from the last 35 images...")
        cursor.execute('''
            SELECT id, file_data, xml_title, added_date FROM archived_files 
            ORDER BY id DESC LIMIT 35
        ''')
        rows = cursor.fetchall()
        
        if len(rows) < 35:
            print(f"Warning: Only {len(rows)} images available in DB. Using all.")
        
        if not rows:
            print("No images found in the database.")
            sys.exit(0)
        
        # DEBUG: Print all fetched titles
        print("\nDEBUG: Fetched titles for the last 35 images:")
        for i, (row_id, file_data, title, added_date_str) in enumerate(rows):
            print(f"  Image {i+1} (ID {row_id}): '{title}'")
        
        image_arrays = []
        duration_per_image = 4  # seconds
        fps = 24
        target_width, target_height = 1920, 1088  # Divisible by 16 to avoid resizing warning
        image_ids = []  # Track IDs for update
        
        for i, (row_id, file_data, title, added_date_str) in enumerate(rows):
            print(f"\nProcessing image {i+1} (ID {row_id}) with title: '{title}'")
            try:
                # Create black starry background
                bg = Image.new('RGB', (target_width, target_height), (0, 0, 0))
                add_stars(bg)
                
                # Load and resize image preserving aspect ratio
                img = Image.open(io.BytesIO(file_data)).convert('RGB')
                img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
                
                # Center the image on background
                paste_x = (target_width - img.width) // 2
                paste_y = (target_height - img.height) // 2
                bg.paste(img, (paste_x, paste_y))
                
                # Add text overlay if title exists
                if title:
                    bar_height = 150
                    bar = Image.new('RGBA', (target_width, bar_height), (0, 0, 0, 128))
                    draw = ImageDraw.Draw(bar)
                    try:
                        font = ImageFont.truetype("roboto.ttf", 26)
                    except:
                        try:
                            font = ImageFont.truetype("arial.ttf", 26)
                        except:
                            font = ImageFont.load_default()
                    
                    lines = textwrap.wrap(title, width=60)
                    y_offset = 20
                    for line in lines:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        text_width = bbox[2] - bbox[0]
                        if text_width > target_width - 100:
                            max_chars = int(len(line) * (target_width - 100) / text_width)
                            line = line[:max_chars] + "..."
                        text_x = (target_width - text_width) // 2
                        draw.text((text_x, y_offset), line, fill=(255, 255, 255, 255), font=font)
                        y_offset += 35
                    
                    bg_rgba = bg.convert('RGBA')
                    bar_full = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
                    bar_full.paste(bar, (0, target_height - bar_height))
                    bg = Image.alpha_composite(bg_rgba, bar_full).convert('RGB')
                else:
                    print(f"  No title for this image, skipping overlay.")
                
                img_array = np.array(bg)
                image_arrays.append(img_array)
                image_ids.append(row_id)
                
            except Exception as e:
                print(f"  Error: {e}")
                continue
        
        if image_arrays:
            # Repeat each image for duration
            frames = []
            for img_array in image_arrays:
                num_frames = int(duration_per_image * fps)
                for _ in range(num_frames):
                    frames.append(img_array)
            
            # Use the added_date of the first (most recent) image for filename
            added_date_str = rows[0][3]
            try:
                date_obj = datetime.strptime(added_date_str, '%Y-%m-%d %H:%M:%S')
                date_str = date_obj.strftime('%Y%m%d')
            except:
                date_str = 'unknown'
            
            temp_video = os.path.join(os.getcwd(), f'{date_str}_temp_slideshow.mp4')
            output_video = os.path.join(os.getcwd(), f'{date_str}_slideshow.mp4')
            
            # Create video without audio using imageio
            imageio.mimsave(temp_video, frames, fps=fps, codec='libx264', quality=8, macro_block_size=1)
            print(f"\nTemporary video created: {temp_video}")
            
            # Add audio using ffmpeg-python
            try:
                if not os.path.exists(AUDIO_FILE):
                    raise FileNotFoundError(f"Audio file not found: {AUDIO_FILE}")
                
                # Check if FFmpeg is installed
                try:
                    ffmpeg.probe(temp_video)  # Test FFmpeg functionality
                except ffmpeg.Error as e:
                    raise Exception("FFmpeg not found or not working. Ensure FFmpeg is installed and in PATH.") from e
                
                # Remove existing output file if it exists
                if os.path.exists(output_video):
                    os.remove(output_video)
                    print(f"Removed existing output file: {output_video}")
                
                # FFmpeg input streams
                video_stream = ffmpeg.input(temp_video)
                audio_stream = ffmpeg.input(AUDIO_FILE)
                
                # Get video duration
                total_duration = len(image_arrays) * duration_per_image
                
                # Merge video and audio
                output_stream = ffmpeg.output(
                    video_stream,
                    audio_stream,
                    output_video,
                    vcodec='copy',  # Copy video stream without re-encoding
                    acodec='aac',   # Encode audio to AAC
                    shortest=None,  # Let audio loop if shorter than video
                    **{'b:a': '192k'},  # Audio bitrate
                    **{'t': total_duration}  # Set output duration to video duration
                )
                
                # Run FFmpeg command
                ffmpeg.run(output_stream, overwrite_output=True)
                print(f"\nVideo with audio created successfully: {output_video}")
                
                # Clean up temporary video
                os.remove(temp_video)
                print(f"Temporary video deleted: {temp_video}")
                
            except Exception as e:
                print(f"Error adding audio: {e}")
                print(f"Keeping video without audio: {temp_video}")
                # Remove existing output file if it exists before renaming
                if os.path.exists(output_video):
                    os.remove(output_video)
                    print(f"Removed existing output file: {output_video}")
                os.rename(temp_video, output_video)
                print(f"Renamed temporary video to: {output_video}")
            
            # Update VideoAirDate for the used images
            current_timestamp = datetime.now().strftime('%Y-%m-%d %H')
            update_data = [(current_timestamp, img_id) for img_id in image_ids]
            cursor.executemany('UPDATE archived_files SET VideoAirDate = ? WHERE id = ?', update_data)
            conn.commit()
            print(f"Updated VideoAirDate '{current_timestamp}' for {len(image_ids)} images.")
        else:
            print("No valid images to create video.")
    
    except Exception as e:
        print(f"Operation failed: {e}")
        # Clean up temporary video if it exists
        if 'temp_video' in locals() and os.path.exists(temp_video):
            os.remove(temp_video)
            print(f"Temporary video deleted due to error: {temp_video}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    main()