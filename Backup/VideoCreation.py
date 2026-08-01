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
    """Process a regular image from DB data."""
    try:
        bg = Image.new('RGB', (target_width, target_height), (0, 0, 0))
        add_stars(bg)
        img = Image.open(io.BytesIO(file_data)).convert('RGB')
        
        min_width_threshold = target_width * 0.6
        min_height_threshold = target_height * 0.6
        img_width, img_height = img.size
        
        scale_factor = 1.0
        if img_width < min_width_threshold or img_height < min_height_threshold:
            scale_factor = max(
                min_width_threshold / img_width,
                min_height_threshold / img_height,
                1.5
            )
            scale_factor = min(scale_factor, 4.0)
        
        new_width = int(img_width * scale_factor)
        new_height = int(img_height * scale_factor)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        
        paste_x = (target_width - img.width) // 2
        paste_y = (target_height - img.height) // 2
        bg.paste(img, (paste_x, paste_y))
        
        if save_count[0] < max_save:
            filename = f"image_{row_id}.png"
            filepath = os.path.join(output_dir, filename)
            bg.save(filepath, format='PNG')
            print(f"Saved image {save_count[0] + 1} of {max_save}: {filepath}")
            save_count[0] += 1
        
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
        
        return np.array(bg), row_id
    except Exception as e:
        print(f"Error processing image ID {row_id}: {e}")
        return None, None

def process_intro_outro_image(file_data, target_width, target_height, num_frames, fps, is_intro=False):
    """Process intro/outro image."""
    try:
        img = Image.open(file_data).convert('RGB')
        scale_factor = 1.25
        new_width = int(target_width * scale_factor)
        new_height = int(target_height * scale_factor)
        img.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)
        
        frames = []
        for frame_idx in range(num_frames):
            bg = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 255))
            bg = add_stars(bg, num_stars=200, seed=None if is_intro else frame_idx // 50)
            paste_x = (target_width - img.width) // 2
            paste_y = (target_height - img.height) // 2
            bg.paste(img, (paste_x, paste_y))
            frames.append(np.array(bg.convert('RGB')))
        return frames
    except Exception as e:
        print(f"Error processing {'intro' if is_intro else 'outro'}: {e}")
        return None

def main(output_dir):
    DATABASE_NAME = 'universal_image_archive.db'
    AUDIO_FILE1 = r"D:\Dev\TheTimeThen\VideoAssets\Andres Jacque - Skipping [Thematic].mp3"
    AUDIO_FILE2 = r"D:\Dev\TheTimeThen\VideoAssets\Gymnopedie no1 - Satie.mp3"
    OUTRO_AUDIO = r"D:\Dev\TheTimeThen\VideoAssets\Outro - The Time Then.mp4"
    INTRO_IMAGE = r"D:\Dev\TheTimeThen\VideoAssets\Logo.jpg"
    
    os.makedirs(output_dir, exist_ok=True)
    if not os.access(output_dir, os.W_OK):
        raise PermissionError(f"No write permission for directory: {output_dir}")
    
    last_part = os.path.basename(os.path.normpath(output_dir))
    conn = create_image_db(DATABASE_NAME)
    cursor = conn.cursor()
    
    fps = 24
    intro_duration = 3.5  # Fixed
    outro_duration = 10.0  # Fixed
    total_video_duration = 570.0  # 9 minutes 30 seconds (3.5s intro + 556.5s images + 10s outro)
    
    # Process intro
    num_frames_intro = int(intro_duration * fps)  # 84 frames
    intro_frames = []
    if os.path.exists(INTRO_IMAGE):
        intro_frames = process_intro_outro_image(INTRO_IMAGE, 1920, 1088, num_frames_intro, fps, is_intro=True)
        print(f"Added {num_frames_intro} intro frames.")
    else:
        print("No intro image found.")
    
    # Process outro
    cursor.execute("SELECT id, file_data, xml_title FROM archived_files WHERE xml_title = 'outro' LIMIT 1")
    outro_row = cursor.fetchone()
    num_frames_outro = int(outro_duration * fps)  # 240 frames
    outro_frames = None
    if outro_row:
        outro_frames = process_intro_outro_image(io.BytesIO(outro_row[1]), 1920, 1088, num_frames_outro, fps, is_intro=False)
        print(f"Added {num_frames_outro} outro frames.")
    
    # Fetch regular images
    cursor.execute("SELECT id, file_data, xml_title FROM archived_files WHERE xml_title NOT IN ('intro', 'outro') AND VideoAirDate = '' ORDER BY id DESC LIMIT 35")
    rows = cursor.fetchall()
    
    image_arrays = []
    save_count = [0]
    current_timestamp = datetime.now().strftime('%Y-%m-%d %H')
    
    for i, row in enumerate(rows, 1):
        row_id, file_data, title = row
        print(f"Processing regular image {i} (ID {row_id}): '{title}'")
        img_array, proc_id = process_regular_image(row_id, file_data, title, 1920, 1088, output_dir, save_count)
        if img_array is not None:
            image_arrays.append(img_array)
            cursor.execute('UPDATE archived_files SET VideoAirDate = ? WHERE id = ?', (current_timestamp, proc_id))
            conn.commit()
            print(f"Updated VideoAirDate to '{current_timestamp}' for image ID {proc_id}")
    
    conn.close()
    
    if not image_arrays:
        print("No valid images found.")
        return
    
    # Calculate duration per image
    regular_images_duration = total_video_duration - intro_duration - outro_duration  # 556.5 seconds
    duration_per_image = regular_images_duration / len(image_arrays)  # ~15.9 seconds
    print(f"Duration per image: {duration_per_image:.2f} seconds")
    
    # Generate frames
    frames = []
    if intro_frames:
        frames.extend(intro_frames)
    
    for i, img_array in enumerate(image_arrays, 1):
        num_frames = int(duration_per_image * fps)  # ~382 frames
        frames.extend([img_array] * num_frames)
        print(f"Added {num_frames} frames for image {i}")
    
    if outro_frames:
        frames.extend(outro_frames)
    
    total_frames = len(frames)
    calculated_duration = total_frames / fps
    print(f"Total frames: {total_frames}, Calculated duration: {calculated_duration:.2f} seconds")
    
    # Ensure total duration is correct
    expected_frames = int(total_video_duration * fps)  # 13680 frames
    if total_frames > expected_frames:
        frames = frames[:expected_frames]
        print(f"Trimmed frames to {expected_frames} to match target duration of {total_video_duration} seconds")
    
    temp_video = os.path.join(output_dir, f"{last_part}_temp_slideshow.mp4")
    final_video = os.path.join(output_dir, f"{last_part}_slideshow.mp4")
    
    # Save temporary video
    imageio.mimsave(temp_video, frames, fps=fps, codec='libx264', quality=8)
    print(f"Temporary video created: {temp_video}")
    
    # Add audio and enforce duration
    try:
        # Trim audio to exact durations
        audio1 = ffmpeg.input(AUDIO_FILE1).audio.filter('atrim', end=regular_images_duration/2)
        audio2 = ffmpeg.input(AUDIO_FILE2).audio.filter('atrim', end=regular_images_duration/2)
        outro_audio = ffmpeg.input(OUTRO_AUDIO).audio.filter('atrim', end=outro_duration)
        combined_audio = ffmpeg.filter([audio1, audio2, outro_audio], 'concat', n=3, v=0, a=1)
        
        # Trim video to exact duration
        video_stream = ffmpeg.input(temp_video).video.filter('trim', duration=total_video_duration).filter('setpts', 'PTS-STARTPTS')
        output = ffmpeg.output(
            video_stream, combined_audio, final_video,
            vcodec='copy', acodec='aac', t=total_video_duration, **{'b:a': '192k'}
        )
        ffmpeg.run(output, overwrite_output=True)
        print(f"Video with audio created successfully: {final_video}")
    except Exception as e:
        print(f"Error adding audio: {e}")
        os.rename(temp_video, final_video)
        print(f"Video without audio created: {final_video}")
    finally:
        if os.path.exists(temp_video):
            os.remove(temp_video)
            print(f"Temporary video deleted: {temp_video}")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) != 2:
        print("Usage: python videoCreation.py <output_directory>")
        sys.exit(1)
    main(sys.argv[1])