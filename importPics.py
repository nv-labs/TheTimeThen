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
import tempfile

def create_image_db(db_name='universal_image_archive.db'):
    """Creates or updates a database for storing files and metadata."""
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
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
        x = random.randint(0, max(0, w - 1))
        y = random.randint(0, max(0, h - 1))
        size = random.randint(1, 2)
        draw.ellipse((x - size, y - size, x + size, y + size), fill=(255, 255, 255))

def process_regular_image(row_id, file_data, title, target_width, target_height):
    """Process a regular image from DB data: bg, stars, resize, center, title overlay."""
    try:
        # Create black background
        bg = Image.new('RGB', (target_width, target_height), (0, 0, 0))
        add_stars(bg)
        
        # Load and prepare image
        img = Image.open(io.BytesIO(file_data)).convert('RGB')
        img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        # Center paste
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
        
        return np.array(bg), row_id
    except Exception as e:
        print(f"Error processing regular image ID {row_id}: {e}")
        return None, None

def process_intro_outro_image(file_data, target_width, target_height):
    """Process intro/outro image: resize to target size, no text, no stars, no bg."""
    try:
        # Accept file path, bytes, or file-like object
        if isinstance(file_data, (bytes, bytearray)):
            fp = io.BytesIO(file_data)
        else:
            fp = file_data
        img = Image.open(fp).convert('RGB')
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        return np.array(img)
    except Exception as e:
        print(f"Error processing intro/outro image: {e}")
        return None

def main():
    DATABASE_NAME = 'universal_image_archive.db'
    AUDIO_FILE1 = r"D:\Dev\automation\VideoAssets\Andres Jacque - Skipping [Thematic].mp3"  # Path to first audio file
    AUDIO_FILE2 = r"D:\Dev\automation\VideoAssets\Gymnopedie no1 - Satie.mp3"  # Path to second audio file
    INTRO_IMAGE = r"D:\Dev\TheTimeThen\VideoAssets\Logo.jpg"  # Path to intro image
    
    # No command-line arguments needed
    if len(sys.argv) > 1:
        print("No arguments needed. Usage: python vidCreate.py")
        sys.exit(1)
    
    conn = None
    
    try:
        conn = create_image_db(DATABASE_NAME)
        cursor = conn.cursor()
        
        # Load intro image from file
        intro_array = None
        if os.path.exists(INTRO_IMAGE):
            intro_array = process_intro_outro_image(INTRO_IMAGE, 1920, 1088)
            print("Processed intro image from Logo.jpg (no text).")
        else:
            print(f"Intro image not found at {INTRO_IMAGE}.")
        
        # Fetch outro image from database
        cursor.execute("SELECT id, file_data, xml_title, added_date FROM archived_files WHERE xml_title = 'outro' LIMIT 1")
        outro_row = cursor.fetchone()
        outro_array = None
        outro_id = None
        if outro_row:
            outro_array = process_intro_outro_image(io.BytesIO(outro_row[1]), 1920, 1088)
            outro_id = outro_row[0]
            print("Processed outro image from database (no text).")
        else:
            print("No outro image found in DB.")
        
        # Fetch the last 35 regular images, excluding 'intro' and 'outro' titles
        print("Creating video from the last 35 regular images (excluding intro/outro)...")
        cursor.execute('''
            SELECT id, file_data, xml_title, added_date FROM archived_files 
            WHERE xml_title NOT IN ('intro', 'outro')
            ORDER BY id DESC LIMIT 35
        ''')
        rows = cursor.fetchall()
        
        if len(rows) < 35:
            print(f"Warning: Only {len(rows)} regular images available in DB. Using all.")
        
        if not rows and intro_array is None and outro_array is None:
            print("No images found in the database or file system.")
            sys.exit(0)
        
        # DEBUG: Print all fetched titles
        print("\nDEBUG: Fetched titles for the last 35 regular images:")
        for i, (row_id, file_data, title, added_date_str) in enumerate(rows):
            print(f"  Image {i+1} (ID {row_id}): '{title}'")
        
        image_arrays = []
        duration_per_image = 4  # seconds
        fps = 24
        target_width, target_height = 1920, 1088  # Divisible by 16 to avoid resizing warning
        image_ids = []  # Track IDs for update
        
        for i, row in enumerate(rows):
            row_id, file_data, title, added_date_str = row
            print(f"\nProcessing regular image {i+1} (ID {row_id}) with title: '{title}'")
            img_array, proc_id = process_regular_image(row_id, file_data, title, target_width, target_height)
            if img_array is not None:
                image_arrays.append(img_array)
                image_ids.append(proc_id)
        
        if image_arrays or intro_array is not None or outro_array is not None:
            # Create frames
            frames = []
            
            # Add intro frames first
            intro_duration = 2  # seconds
            if intro_array is not None:
                num_frames_intro = int(intro_duration * fps)
                for _ in range(num_frames_intro):
                    frames.append(intro_array)
                print(f"Added {num_frames_intro} intro frames from Logo.jpg (image only).")
            
            # Add slideshow frames
            for img_array in image_arrays:
                num_frames = int(duration_per_image * fps)
                for _ in range(num_frames):
                    frames.append(img_array)
            
            # Add outro frames last
            outro_duration = 2  # seconds
            if outro_array is not None:
                num_frames_outro = int(outro_duration * fps)
                for _ in range(num_frames_outro):
                    frames.append(outro_array)
                print(f"Added {num_frames_outro} outro frames from database (image only).")
                if outro_id and outro_id not in image_ids:
                    image_ids.append(outro_id)  # Include in update
            
            # Use the added_date of the first (most recent) image for filename
            added_date_str = rows[0][3] if rows else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                date_obj = datetime.strptime(added_date_str, '%Y-%m-%d %H:%M:%S')
                date_str = date_obj.strftime('%Y%m%d')
            except:
                date_str = 'unknown'
            
            output_video = os.path.join(os.getcwd(), f'{date_str}_slideshow.mp4')

            # Create video without audio using a safe temporary file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmpf:
                temp_video = tmpf.name

            try:
                writer = imageio.get_writer(temp_video, fps=fps, codec='libx264', quality=8)
                for frame in frames:
                    writer.append_data(frame)
                writer.close()
                print(f"\nTemporary video created: {temp_video}")
            except Exception:
                if os.path.exists(temp_video):
                    try:
                        os.remove(temp_video)
                    except Exception:
                        pass
                raise
            
            # Add audio using ffmpeg-python
            try:
                if not os.path.exists(AUDIO_FILE1) or not os.path.exists(AUDIO_FILE2):
                    raise FileNotFoundError(f"One or both audio files not found: {AUDIO_FILE1}, {AUDIO_FILE2}")
                
                # Check if FFmpeg is installed
                try:
                    ffmpeg.probe(temp_video)  # Test FFmpeg functionality
                except ffmpeg.Error as e:
                    raise Exception("FFmpeg not found or not working. Ensure FFmpeg is installed and in PATH.") from e
                
                # Remove existing output file if it exists
                if os.path.exists(output_video):
                    os.remove(output_video)
                    print(f"Removed existing output file: {output_video}")
                
                # Get video duration
                slideshow_duration = len(image_arrays) * duration_per_image
                total_duration = slideshow_duration + (intro_duration if intro_array is not None else 0) + (outro_duration if outro_array is not None else 0)
                half_duration = total_duration / 2.0
                
                # Create combined audio: first half from AUDIO_FILE1, second half from AUDIO_FILE2
                audio1 = ffmpeg.input(AUDIO_FILE1).audio.filter('atrim', end=half_duration)
                audio2 = ffmpeg.input(AUDIO_FILE2).audio.filter('atrim', end=half_duration)
                combined_audio = ffmpeg.filter([audio1, audio2], 'concat', n=2, v=0, a=1)
                
                # FFmpeg input streams
                video_stream = ffmpeg.input(temp_video)
                
                # Merge video and combined audio
                output_stream = ffmpeg.output(
                    video_stream,
                    combined_audio,
                    output_video,
                    vcodec='copy',  # Copy video stream without re-encoding
                    acodec='aac',   # Encode audio to AAC
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
            
            # Update VideoAirDate for the used images (regular images and outro)
            if image_ids:
                current_timestamp = datetime.now().strftime('%Y-%m-%d %H')
                update_data = [(current_timestamp, img_id) for img_id in image_ids if img_id is not None]
                cursor.executemany('UPDATE archived_files SET VideoAirDate = ? WHERE id = ?', update_data)
                conn.commit()
                print(f"Updated VideoAirDate '{current_timestamp}' for {len(update_data)} images.")
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