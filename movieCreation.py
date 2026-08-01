import os
import sys
import sqlite3
from PIL import Image, ImageDraw
import io
import numpy as np
import imageio
import random
from datetime import datetime
import ffmpeg

def connect_to_db(db_name='universal_image_archive.db'):
    """Connect to the existing database."""
    try:
        conn = sqlite3.connect(db_name)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error connecting to database {db_name}: {e}")
        sys.exit(1)

def add_stars(bg_img, num_stars=200, seed=None):
    """Add random white stars to the background image with optional seed."""
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

def process_intro_outro_image(file_data, target_width, target_height, num_frames, fps, is_intro=False):
    """Process intro/outro image: resize to fit, center on starry background."""
    try:
        img = Image.open(io.BytesIO(file_data)).convert('RGB')
        scale_factor = 1.25
        new_width = int(target_width * scale_factor)
        new_height = int(target_height * scale_factor)
        img.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)
        
        bg = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 255))
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
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error processing {'intro' if is_intro else 'outro'} image: {e}")
        return None

def create_intro_outro_video(frames, output_path, fps):
    """Create a video from intro or outro frames."""
    try:
        imageio.mimsave(output_path, frames, fps=fps, codec='libx264', quality=8, macro_block_size=1)
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Created video: {output_path}")
        return True
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error creating video {output_path}: {e}")
        return False

def main(input_folder):
    """Create a video by adding intro and outro to the video in the input folder."""
    DATABASE_NAME = 'universal_image_archive.db'
    AUDIO_FILE1 = r"D:\Dev\TheTimeThen\VideoAssets\Andres Jacque - Skipping [Thematic].mp3"
    AUDIO_FILE2 = r"D:\Dev\TheTimeThen\VideoAssets\Gymnopedie no1 - Satie.mp3"
    OUTRO_AUDIO = r"D:\Dev\TheTimeThen\VideoAssets\Outro - The Time Then.mp4"
    
    # Validate input folder
    if not os.path.isdir(input_folder):
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Input folder {input_folder} does not exist.")
        sys.exit(1)
    
    output_dir = input_folder
    last_part = os.path.basename(os.path.normpath(input_folder))
    
    # Ensure output directory is writable
    try:
        os.makedirs(output_dir, exist_ok=True)
        if not os.access(output_dir, os.W_OK):
            raise PermissionError(f"No write permission for directory: {output_dir}")
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error accessing output directory {output_dir}: {e}")
        sys.exit(1)
    
    conn = None
    temp_files = []
    
    try:
        # Connect to database
        conn = connect_to_db(DATABASE_NAME)
        cursor = conn.cursor()
        
        # Find the video file
        video_extensions = ('.mp4',)
        video_files = [
            f for f in os.listdir(input_folder)
            if os.path.isfile(os.path.join(input_folder, f)) and f.lower().endswith(video_extensions)
        ]
        # Filter out any '_final.mp4' files to avoid using previous outputs
        video_files = [f for f in video_files if not f.endswith('_final.mp4')]
        if not video_files:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No video files (.mp4) found in folder {input_folder} (excluding *_final.mp4).")
            sys.exit(0)
        if len(video_files) > 1:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Warning: Multiple video files found: {video_files}. Using: Memphis4k.mp4")
            main_video_path = os.path.join(input_folder, 'Memphis4k.mp4')
            if not os.path.exists(main_video_path):
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error: Preferred video 'Memphis4k.mp4' not found, using {video_files[0]}")
                main_video_path = os.path.join(input_folder, video_files[0])
        else:
            main_video_path = os.path.join(input_folder, video_files[0])
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Found video: {main_video_path}")
        
        # Verify main video
        try:
            probe = ffmpeg.probe(main_video_path)
            main_duration = float(probe['format']['duration'])
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Main video duration: {main_duration:.2f} seconds")
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error probing main video {main_video_path}: {e}")
            sys.exit(1)
        
        # Fetch intro image from database
        cursor.execute("SELECT id, file_data FROM archived_files WHERE xml_title = 'intro' LIMIT 1")
        intro_row = cursor.fetchone()
        intro_frames = None
        intro_id = None
        intro_duration = 3.5
        fps = 24
        num_frames_intro = int(intro_duration * fps)
        intro_video = os.path.join(output_dir, f'{last_part}_intro.mp4')
        if intro_row:
            intro_id = intro_row['id']
            intro_data = intro_row['file_data']
            intro_frames = process_intro_outro_image(intro_data, 1920, 1088, num_frames_intro, fps, is_intro=True)
            if intro_frames and create_intro_outro_video(intro_frames, intro_video, fps):
                temp_files.append(intro_video)
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Processed intro video (static stars).")
            else:
                intro_frames = None
        else:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No intro image found in database (xml_title = 'intro').")
        
        # Fetch outro image from database
        cursor.execute("SELECT id, file_data FROM archived_files WHERE xml_title = 'outro' LIMIT 1")
        outro_row = cursor.fetchone()
        outro_frames = None
        outro_id = None
        outro_duration = 16
        num_frames_outro = int(outro_duration * fps)
        outro_video = os.path.join(output_dir, f'{last_part}_outro.mp4')
        if outro_row:
            outro_id = outro_row['id']
            outro_data = outro_row['file_data']
            outro_frames = process_intro_outro_image(outro_data, 1920, 1088, num_frames_outro, fps, is_intro=False)
            if outro_frames and create_intro_outro_video(outro_frames, outro_video, fps):
                temp_files.append(outro_video)
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Processed outro video (animated stars).")
            else:
                outro_frames = None
        else:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No outro image found in database (xml_title = 'outro').")
        
        # Check if we have at least the main video
        if not intro_frames and not outro_frames and not os.path.exists(main_video_path):
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: No valid video or intro/outro images to process.")
            sys.exit(0)
        
        # Update VideoAirDate for intro/outro
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H')
        if intro_id:
            cursor.execute('UPDATE archived_files SET VideoAirDate = ? WHERE id = ?', (current_timestamp, intro_id))
            conn.commit()
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Updated VideoAirDate to '{current_timestamp}' for intro image ID {intro_id}")
        if outro_id:
            cursor.execute('UPDATE archived_files SET VideoAirDate = ? WHERE id = ?', (current_timestamp, outro_id))
            conn.commit()
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Updated VideoAirDate to '{current_timestamp}' for outro image ID {outro_id}")
        
        # Prepare output video
        output_video = os.path.join(output_dir, f'{last_part}_final.mp4')
        total_duration = intro_duration + main_duration + outro_duration
        
        # Video concatenation
        try:
            video_inputs = []
            if intro_frames:
                video_inputs.append(ffmpeg.input(intro_video).filter('scale', 1920, 1088, force_original_aspect_ratio='decrease').filter('pad', 1920, 1088, '(ow-iw)/2', '(oh-ih)/2').filter('setsar', 1))
            video_inputs.append(ffmpeg.input(main_video_path).video.filter('scale', 1920, 1088, force_original_aspect_ratio='decrease').filter('pad', 1920, 1088, '(ow-iw)/2', '(oh-ih)/2').filter('setsar', 1))
            if outro_frames:
                video_inputs.append(ffmpeg.input(outro_video).filter('scale', 1920, 1088, force_original_aspect_ratio='decrease').filter('pad', 1920, 1088, '(ow-iw)/2', '(oh-ih)/2').filter('setsar', 1))
            
            concat_video = ffmpeg.concat(*video_inputs, v=1, a=0, unsafe=True).node
            concat_video = concat_video['v']
            
            # Audio handling
            if not (os.path.exists(AUDIO_FILE1) and os.path.exists(AUDIO_FILE2) and os.path.exists(OUTRO_AUDIO)):
                raise FileNotFoundError("Missing one or more audio files.")
            
            non_outro_duration = intro_duration + main_duration
            audio1_duration = non_outro_duration / 2.0
            audio2_duration = non_outro_duration / 2.0
            audio1 = ffmpeg.input(AUDIO_FILE1).audio.filter('aloop', loop=-1, size='2e9').filter('atrim', end=audio1_duration)
            audio2 = ffmpeg.input(AUDIO_FILE2).audio.filter('aloop', loop=-1, size='2e9').filter('atrim', end=audio2_duration)
            outro_audio = ffmpeg.input(OUTRO_AUDIO).audio.filter('aloop', loop=-1, size='2e9').filter('atrim', end=outro_duration)
            combined_audio = ffmpeg.filter([audio1, audio2, outro_audio], 'concat', n=3, v=0, a=1).node
            combined_audio = combined_audio['a']
            
            output_stream = ffmpeg.output(
                concat_video,
                combined_audio,
                output_video,
                vcodec='libx264',
                acodec='aac',
                **{'b:a': '192k'},
                **{'t': total_duration},
                pix_fmt='yuv420p',
                map='[v]',
                map2='[a]'
            )
            
            ffmpeg.run(output_stream, overwrite_output=True, capture_stderr=True)
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Video with audio created successfully: {output_video}")
        
        except ffmpeg.Error as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Error during video concatenation or audio processing: {e.stderr.decode()}")
            sys.exit(1)
        
    except Exception as e:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Operation failed: {e}")
        sys.exit(1)
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: Deleted temporary file: {temp_file}")
        if conn:
            conn.close()

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) != 2:
        print("Usage: python create_video_with_intro_outro.py <input_folder>")
        print("Example: python create_video_with_intro_outro.py 'D:\\Youtube\\TTT\\Movie20251018'")
        sys.exit(1)
    main(sys.argv[1])