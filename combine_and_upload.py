#!/usr/bin/env python3
"""
Wrapper script that:
1. Runs combine_dbs_slideshow with provided parameters
2. Uses the --outdir value as input to upload_youtube_video

Usage example:
    python combine_and_upload.py --db1 d:/Dev/TheTimeThen/universal_image_archive.db --db1-table photos_2023_photos --db2 d:/Dev/TheTimeThen/image_collection.db --db2-table image_comp --total 35 --pct1 60 --outdir out

This will:
- Create slideshow in 'out' directory
- Automatically upload the generated video to YouTube
"""
import subprocess
import sys
import os
import argparse
import time
from datetime import datetime


def run_command(cmd, description, retry_count=1, retry_delay=5):
    """Run a command with optional retry logic.
    
    Args:
        cmd: Command to run
        description: Description of the command
        retry_count: Number of times to retry on failure (1 = no retry)
        retry_delay: Initial delay between retries in seconds
    
    Returns:
        True if successful, False otherwise
    """
    for attempt in range(retry_count):
        print(f"\n{'='*80}")
        if attempt > 0:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: {description} (retry {attempt}/{retry_count-1})")
        else:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: {description}")
        print(f"Command: {' '.join(cmd)}")
        print(f"{'='*80}\n")
        
        result = subprocess.run(cmd)
        
        if result.returncode == 0:
            print(f"\n✅ {description} completed successfully")
            return True
        
        if attempt < retry_count - 1:
            wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
            print(f"\n⚠️  {description} failed (attempt {attempt+1}/{retry_count})")
            print(f"   Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            print(f"\n⚠️  {description} failed after {retry_count} attempt(s)")
    
    return False


def main():
    # Parse arguments for combine_dbs_slideshow
    parser = argparse.ArgumentParser(
        description="Combine images from two DBs and upload to YouTube"
    )
    parser.add_argument("--db1", required=True, help="Path to DB used by VideoCreation2")
    parser.add_argument("--db1-table", default="photos_2023_photos")
    parser.add_argument("--db1-title-col", default="xml_title")
    parser.add_argument("--db2", required=True, help="Path to DB used by VideoFromPhotosTable")
    parser.add_argument("--db2-table", default="image_comp")
    parser.add_argument("--db2-title-col", default="description")
    parser.add_argument("--total", type=int, default=35)
    parser.add_argument("--pct1", type=int, default=50)
    parser.add_argument("--n1", type=int, default=None)
    parser.add_argument("--n2", type=int, default=None)
    parser.add_argument("--outdir", required=True, help="Output directory for video")
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument("--air-date", help="Scheduled air date of the video (YYYY-MM-DD HH:MM:SS)")
    
    args = parser.parse_args()
    
    # Get the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    combine_script = os.path.join(script_dir, "combine_dbs_slideshow.py")
    thumbnail_script = os.path.join(script_dir, "create_thumbnail.py")
    upload_script = os.path.join(script_dir, "upload_youtube_video.py")
    
    # Verify scripts exist
    if not os.path.isfile(combine_script):
        print(f"❌ combine_dbs_slideshow.py not found at {combine_script}")
        sys.exit(1)
    if not os.path.isfile(thumbnail_script):
        print(f"❌ create_thumbnail.py not found at {thumbnail_script}")
        sys.exit(1)
    if not os.path.isfile(upload_script):
        print(f"❌ upload_youtube_video.py not found at {upload_script}")
        sys.exit(1)
    
    # Build command for combine_dbs_slideshow
    combine_cmd = [
        sys.executable,
        combine_script,
        "--db1", args.db1,
        "--db1-table", args.db1_table,
        "--db1-title-col", args.db1_title_col,
        "--db2", args.db2,
        "--db2-table", args.db2_table,
        "--db2-title-col", args.db2_title_col,
        "--total", str(args.total),
        "--pct1", str(args.pct1),
        "--outdir", args.outdir,
    ]
    
    if args.n1 is not None:
        combine_cmd.extend(["--n1", str(args.n1)])
    if args.n2 is not None:
        combine_cmd.extend(["--n2", str(args.n2)])
    if args.skip_audio:
        combine_cmd.append("--skip-audio")
    if getattr(args, 'air_date', None):
        combine_cmd.extend(["--air-date", args.air_date])
    
    # Run combine_dbs_slideshow (strict - must succeed)
    if not run_command(combine_cmd, "Running combine_dbs_slideshow"):
        sys.exit(1)

    # Create an associated thumbnail for the generated video output folder using cleaned images.
    thumbnail_path = os.path.join(args.outdir, "thumbnail.jpg")
    thumbnail_cmd = [
        sys.executable,
        thumbnail_script,
        "--folder",
        args.outdir,
        "--output",
        thumbnail_path,
    ]
    if not run_command(thumbnail_cmd, "Running create_thumbnail with clean folder images"):
        sys.exit(1)
    
    # Run upload_youtube_video with outdir as argument (retry up to 3 times with exponential backoff)
    upload_cmd = [sys.executable, upload_script, args.outdir]
    upload_success = run_command(upload_cmd, "Running upload_youtube_video", retry_count=3, retry_delay=10)
    
    print(f"\n{'='*80}")
    if upload_success:
        print(f"✅ All done! Slideshow created and uploaded to YouTube.")
    else:
        print(f"⚠️  Slideshow created successfully:")
        print(f"   {os.path.join(args.outdir, 'combined_slideshow.mp4')}")
        print(f"")
        print(f"   Upload to YouTube failed after 3 attempts.")
        print(f"   You can retry manually with:")
        print(f"   python upload_youtube_video.py \"{args.outdir}\"")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
