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
import ffmpeg
import re

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

def add_stars(bg_img, num_stars=200, seed=None):
    """Add random white stars to the background image with optional seed for variation."""
    if seed is not None:
        random.seed(seed)
    w, h = bg_img.size
    draw = ImageDraw.Draw(bg_img)
    for _ in range(num_stars):
        x = random.randint(0, w)
        y = random.randint(0, h)
        size = random.randint(1, 2)
        opacity = random.randint(128, 255)
        draw.ellipse((x - size, y - size, x + size, y + size), fill=(255, 255, 255, opacity))
    return bg_img

def process_regular_image(row_id, file_data, title, target_width, target_height, output_dir, save_count, max_save=20):
    """Process a regular image from DB data: background, stars, enlarge if small, center, title overlay, and save if within limit."""
    try:
        # Create black background
        bg = Image.new('RGB', (target_width, target_height), (0, 0, 0))
        add_stars(bg)
        
        # Load and prepare image
        img = Image.open(io.BytesIO(file_data)).convert('RGB')
        
        # Check if image is too small (e.g., less than 60% of target dimensions)
        min_width_threshold = target_width * 0.6
        min_height_threshold = target_height * 0.6
        img_width, img_height = img.size
        
        # Calculate scaling factor to ensure image meets minimum size
        scale_factor = 1.0
        if img_width < min_width_threshold or img_height < min_height_threshold:
            scale_factor = max(
                min_width_threshold / img_width,
                min_height_threshold / img_height,
                1.5
            )
            scale_factor = min(scale_factor, 4.0)
        
        # Resize image while preserving aspect ratio
        new_width = int(img_width * scale_factor)
        new_height = int(img_height * scale_factor)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Ensure image fits within target dimensions
        img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        
        # Center paste
        paste_x = (target_width - img.width) // 2
        paste_y = (target_height - img.height) // 2
        bg.paste(img, (paste_x, paste_y))
        
        # Add text overlay if title exists
        if title:
            try:
                font = ImageFont.truetype("roboto.ttf", 42)
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", 42)
                except:
                    font = ImageFont.load_default()
            
            lines = textwrap.wrap(title, width=80)
            line_height = 55
            padding = 20
            bar_height = len(lines) * line_height + 2 * padding
            
            bar = Image.new('RGBA', (target_width, bar_height), (0, 0, 0, 128))
            draw = ImageDraw.Draw(bar)
            
            y_offset = padding
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                if text_width > target_width - 2 * padding:
                    max_chars = int(len(line) * (target_width - 2 * padding) / text_width)
                    line = line[:max_chars] + "..."
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_width = bbox[2] - bbox[0]
                text_x = (target_width - text_width) // 2
                draw.text((text_x, y_offset), line, fill=(255, 255, 255, 255), font=font)
                y_offset += line_height
            
            bg_rgba = bg.convert('RGBA')
            bar_full = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
            bar_full.paste(bar, (0, target_height - bar_height))
            bg = Image.alpha_composite(bg_rgba, bar_full).convert('RGB')
        
        # Save the image if within the limit
        if save_count[0] < max_save:
            # Sanitize title for filename
            safe_title = re.sub(r'[^\w\s-]', '_', title or 'untitled').strip()
            safe_title = re.sub(r'\s+', '_', safe_title)
            filename = f"image_{row_id}_{safe_title}.png"
            filepath = os.path.join(output_dir, filename)
            bg.save(filepath, format='PNG')
            print(f"Saved image {save_count[0] + 1} of {max_save}: {filepath}")
            save_count[0] += 1
        
        return np.array(bg), row_id
    except Exception as e:
        print(f"Error processing regular image ID {row_id}: {e}")
        return None, None

def process_intro_outro_image(file_data, target_width, target_height, num_frames, fps, is_intro=False):
    """Process intro/outro image: resize to fit, center on starry background."""
    try:
        img = Image.open(file_data).convert('RGB')

        scale_factor = 1.25
        new_width = int(target_width * scale_factor)
        new_height = int(target_height * scale_factor)
        img.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)
        
        bg = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 255))
        seed = None
        
        if is_intro:
            bg = add_stars(bg, num_stars=200, seed=None)
            paste_x = (target_width - img.width) // 2
            paste_y = (target_height - img.height) // 2
            bg.paste(img, (paste_x, paste_y))
            single_frame = np.array(bg.convert('RGB'))
            frames = [single_frame] * num_frames
        else:
            frames = []
            for frame_idx in range(num_frames):
                bg = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 255))
                seed = frame_idx // 50
                bg = add_stars(bg, num_stars=200, seed=seed)
                paste_x = (target_width - img.width) // 2
                paste_y = (target_height - img.height) // 2
                bg.paste(img, (paste_x, paste_y))
                frames.append(np.array(bg.convert('RGB')))
        
        return frames
    except Exception as e:
        print(f"Error processing {'intro' if is_intro else 'outro'} image: {e}")
        return None

def main(output_dir):
    DATABASE_NAME = 'universal_image_archive.db'
    AUDIO_FILE1 = r"D:\Dev\TheTimeThen\VideoAssets\Andres Jacque - Skipping [Thematic].mp3"
    AUDIO_FILE2 = r"D:\Dev\TheTimeThen\VideoAssets\Gymnopedie no1 - Satie.mp3"
    OUTRO_AUDIO = r"D:\Dev\TheTimeThen\VideoAssets\Outro - The Time Then.mp4"
    INTRO_IMAGE = r"D:\Dev\TheTimeThen\VideoAssets\Logo.jpg"
    
    # Ensure output directory exists
    try:
        os.makedirs(output_dir, exist_ok=True)
        if not os.access(output_dir, os.W_OK):
            raise PermissionError(f"No write permission for directory: {output_dir}")
    except Exception as e:
        print(f"Error accessing output directory {output_dir}: {e}")
        sys.exit(1)
    
    last_part = os.path.basename(os.path.normpath(output_dir))
    
    conn = None
    temp_video = None
    
    try:
        conn = create_image_db(DATABASE_NAME)
        cursor = conn.cursor()
        
        # Intro setup
        intro_frames = None
        intro_duration = 3.5
        fps = 24
        num_frames_intro = int(intro_duration * fps)
        if os.path.exists(INTRO_IMAGE):
            intro_frames = process_intro_outro_image(INTRO_IMAGE, 1920, 1088, num_frames_intro, fps, is_intro=True)
            print("Processed intro image (static stars).")
        else:
            print(f"Intro image not found at {INTRO_IMAGE}.")
        
        # Outro setup
        cursor.execute("SELECT id, file_data, xml_title, added_date FROM archived_files WHERE xml_title = 'outro' LIMIT 1")
        outro_row = cursor.fetchone()
        outro_frames = None
        outro_id = None
        if outro_row:
            outro_duration = 16
            num_frames_outro = int(outro_duration * fps)
            outro_frames = process_intro_outro_image(io.BytesIO(outro_row[1]), 1920, 1088, num_frames_outro, fps, is_intro=False)
            outro_id = outro_row[0]
            print("Processed outro image (animated stars).")
        else:
            print("No outro image found in DB.")
        
        # Fetch up to 35 images, with at most 1 having specific words
        print("Creating video from the last 35 regular images with empty VideoAirDate, with at most 1 containing specific words...")
        cursor.execute('''
            SELECT id, file_data, xml_title, added_date FROM (
                SELECT id, file_data, xml_title, added_date
                FROM archived_files 
                WHERE xml_title NOT IN ('intro', 'outro') 
                AND VideoAirDate = ''
                AND (xml_title LIKE '%actress%' OR xml_title LIKE '%singer%' OR xml_title LIKE '%Monroe%' 
                     OR xml_title LIKE '%Rita%' OR xml_title LIKE '%pin up%' OR xml_title LIKE '%Sandra%' 
                     OR xml_title LIKE '%Brigitte%' OR xml_title LIKE '%Emma%' OR xml_title LIKE '%Jessica%')
                ORDER BY id DESC
                LIMIT 1
            ) 
            UNION
            SELECT id, file_data, xml_title, added_date
            FROM archived_files 
            WHERE xml_title NOT IN ('intro', 'outro') 
            AND VideoAirDate = ''
            AND xml_title NOT LIKE '%actress%'
            AND xml_title NOT LIKE '%singer%'
            AND xml_title NOT LIKE '%Monroe%'
            AND xml_title NOT LIKE '%Rita%'
            AND xml_title NOT LIKE '%pin up%'
            AND xml_title NOT LIKE '%Sandra%'
            AND xml_title NOT LIKE '%Brigitte%'
            AND xml_title NOT LIKE '%Emma%'
            AND xml_title NOT LIKE '%Jessica%'
            ORDER BY id DESC
            LIMIT 34
        ''')
        rows = cursor.fetchall()
        
        if len(rows) < 35:
            print(f"Warning: Only {len(rows)} regular images with empty VideoAirDate available. Using all.")
        
        if not rows and intro_frames is None and outro_frames is None:
            print("No images found in the database or file system with empty VideoAirDate.")
            sys.exit(0)
        
        image_arrays = []
        duration_per_image = 17
        target_width, target_height = 1920, 1088
        image_ids = []
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H')
        save_count = [0]  # Use list to allow modification in process_regular_image
        
        # Process images and update VideoAirDate immediately
        for i, row in enumerate(rows):
            row_id, file_data, title, added_date_str = row
            print(f"Processing regular image {i+1} (ID {row_id}): '{title}'")
            img_array, proc_id = process_regular_image(row_id, file_data, title, target_width, target_height, output_dir, save_count)
            if img_array is not None:
                image_arrays.append(img_array)
                image_ids.append(proc_id)
                # Update VideoAirDate immediately after selection
                cursor.execute('UPDATE archived_files SET VideoAirDate = ? WHERE id = ?', (current_timestamp, proc_id))
                conn.commit()
                print(f"Updated VideoAirDate to '{current_timestamp}' for image ID {proc_id}")
        
        if image_arrays or intro_frames or outro_frames:
            frames = []
            
            if intro_frames:
                frames.extend(intro_frames)
                print(f"Added {num_frames_intro} intro frames.")
            
            for img_array in image_arrays:
                num_frames = int(duration_per_image * fps)
                frames.extend([img_array] * num_frames)
            
            if outro_frames:
                frames.extend(outro_frames)
                print(f"Added outro frames ({len(outro_frames)} total).")
                if outro_id and outro_id not in image_ids:
                    image_ids.append(outro_id)
                    # Update VideoAirDate for outro if used
                    cursor.execute('UPDATE archived_files SET VideoAirDate = ? WHERE id = ?', (current_timestamp, outro_id))
                    conn.commit()
                    print(f"Updated VideoAirDate to '{current_timestamp}' for outro image ID {outro_id}")
            
            added_date_str = rows[0][3] if rows else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                date_obj = datetime.strptime(added_date_str, '%Y-%m-%d %H:%M:%S')
                date_str = date_obj.strftime('%Y%m%d')
            except:
                date_str = last_part
            
            temp_video = os.path.join(output_dir, f'{last_part}_temp_slideshow.mp4')
            output_video = os.path.join(output_dir, f'{last_part}_slideshow.mp4')
            
            imageio.mimsave(temp_video, frames, fps=fps, codec='libx264', quality=8, macro_block_size=1)
            print(f"\nTemporary video created: {temp_video}")
            
            # Audio handling
            try:
                if not (os.path.exists(AUDIO_FILE1) and os.path.exists(AUDIO_FILE2) and os.path.exists(OUTRO_AUDIO)):
                    raise FileNotFoundError("Missing one or more audio files.")
                
                ffmpeg.probe(temp_video)
                
                slideshow_duration = len(image_arrays) * duration_per_image
                outro_duration = 16 if outro_frames else 0
                intro_duration = 3.5 if intro_frames else 0
                total_duration = slideshow_duration + intro_duration + outro_duration
                non_outro_duration = total_duration - outro_duration
                audio1_duration = non_outro_duration / 2.0
                audio2_duration = non_outro_duration / 2.0
                
                audio1 = ffmpeg.input(AUDIO_FILE1).audio.filter('aloop', loop=-1, size='2e9').filter('atrim', end=audio1_duration)
                audio2 = ffmpeg.input(AUDIO_FILE2).audio.filter('aloop', loop=-1, size='2e9').filter('atrim', end=audio2_duration)
                outro_audio = ffmpeg.input(OUTRO_AUDIO).audio.filter('atrim', end=outro_duration)
                
                combined_audio = ffmpeg.filter([audio1, audio2, outro_audio], 'concat', n=3, v=0, a=1)
                video_stream = ffmpeg.input(temp_video)
                
                output_stream = ffmpeg.output(
                    video_stream,
                    combined_audio,
                    output_video,
                    vcodec='copy',
                    acodec='aac',
                    **{'b:a': '192k'},
                    **{'t': total_duration}
                )
                
                ffmpeg.run(output_stream, overwrite_output=True)
                print(f"\nVideo with audio created successfully: {output_video}")
            
            except Exception as e:
                print(f"Error adding audio: {e}")
                if os.path.exists(output_video):
                    os.remove(output_video)
                os.rename(temp_video, output_video)
                print(f"Renamed video (without audio): {output_video}")
            finally:
                if temp_video and os.path.exists(temp_video):
                    os.remove(temp_video)
                    print(f"Temporary video deleted: {temp_video}")
        
        else:
            print("No valid images to create video.")
    
    except Exception as e:
        print(f"Operation failed: {e}")
        if temp_video and os.path.exists(temp_video):
            os.remove(temp_video)
            print(f"Temporary video deleted due to error: {temp_video}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) != 2:
        print("Usage: python videoCreation.py <output_directory>")
        sys.exit(1)
    main(sys.argv[1])