#!/usr/bin/env python3
r"""
Run combine_and_upload.py multiple times with correct output directories.

Usage:
    python schedule_bulk_uploads.py 2026-04-03
    
This will run the script 10 times immediately (10 days × 1 time per day at 23h):
    - 2026-04-03: 23h
    - 2026-04-04: 23h
    - 2026-04-05: 23h
    - 2026-04-06: 23h
    - 2026-04-07: 23h
    - 2026-04-08: 23h
    - 2026-04-09: 23h
    - 2026-04-10: 23h
    - 2026-04-11: 23h
    - 2026-04-12: 23h
    
Each run uses the outdir format: D:\Youtube\TTT\2026\MM\YYYYMMdd-HHh
"""

import subprocess
import argparse
from datetime import datetime, timedelta
import os

DEFAULT_PLAYLIST_PREFIX = "Historical Old Photos.."
DEFAULT_AUTO_IMPORT_END_SCREEN = "1"


def run_combine_and_upload(date_obj, hour):
    """Run the combine_and_upload.py script with the appropriate parameters."""
    
    # Format the output directory
    date_str = date_obj.strftime("%Y%m%d")
    month_str = date_obj.strftime("%m")
    hour_str = f"{hour:02d}h"
    outdir = f"D:\\Youtube\\TTT\\2026\\{month_str}\\{date_str}-{hour_str}"
    
    # Format the scheduled air date
    air_date_str = f"{date_obj.strftime('%Y-%m-%d')} {hour:02d}:00:00"
    
    # Use the autos environment Python (has imageio, cv2, etc.)
    python_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "autos", "Scripts", "python.exe")
    
    # Build the command
    cmd = [
        python_exe,
        ".\\combine_and_upload.py",
        "--db1", "d:/Dev/TheTimeThen/google_takeout_photos_2023.db",
        "--db1-table", "photos",
        "--db2", "d:/Dev/TheTimeThen/image_collection.db",
        "--db2-table", "image_comp",
        "--n1", "10",
        "--n2", "25",
        "--outdir", outdir,
        "--air-date", air_date_str
    ]
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[{timestamp}] ► Running for {date_obj.strftime('%Y-%m-%d')} {hour:02d}h")
    print(f"   Output: {outdir}")
    
    try:
        command_env = os.environ.copy()
        command_env.setdefault("YT_PLAYLIST_TITLE_PREFIX", DEFAULT_PLAYLIST_PREFIX)
        command_env.setdefault("YT_AUTO_IMPORT_END_SCREEN", DEFAULT_AUTO_IMPORT_END_SCREEN)
        result = subprocess.run(
            cmd,
            check=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=command_env,
        )
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] ✓ Completed!")
        return True
    except subprocess.CalledProcessError as e:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] ✗ Error: Exit code {e.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run combine_and_upload.py for 5 days, twice per day (14h and 23h)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python schedule_bulk_uploads.py 2026-04-03
  python schedule_bulk_uploads.py 2026-03-28
  python schedule_bulk_uploads.py 2026-04-03 --one-day
        """
    )
    parser.add_argument(
        "start_date",
        help="Start date in format YYYY-MM-DD (e.g., 2026-04-03)"
    )
    parser.add_argument(
        "--one-day",
        action="store_true",
        help="Only process the start date (2 videos: 14h and 23h)"
    )

    args = parser.parse_args()

    # Parse the start date
    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    except ValueError:
        print("❌ Invalid date format. Please use YYYY-MM-DD (e.g., 2026-04-03)")
        return

    # Build all jobs
    jobs = []
    if args.one_day:
        jobs.append((start_date, 23))
        duration_str = "1 day (1 total run)"
    else:
        for day_offset in range(10):
            current_date = start_date + timedelta(days=day_offset)
            jobs.append((current_date, 23))
        duration_str = "10 days (10 total runs)"

    # Display the plan
    print("=" * 70)
    print("BATCH RUNNER: combine_and_upload.py")
    print("=" * 70)
    print(f"Start Date: {start_date.strftime('%Y-%m-%d')}")
    print(f"Duration: {duration_str}")
    print(f"Playlist prefix: {os.environ.get('YT_PLAYLIST_TITLE_PREFIX', DEFAULT_PLAYLIST_PREFIX)}")
    print(f"Auto end screen import: {os.environ.get('YT_AUTO_IMPORT_END_SCREEN', DEFAULT_AUTO_IMPORT_END_SCREEN)}")
    print("\nExecution Plan:")
    print("-" * 70)

    for date_obj, hour in jobs:
        print(f"  {date_obj.strftime('%Y-%m-%d')} {hour:02d}h")

    print("-" * 70)
    print(f"Total: {len(jobs)} executions\n")

    # Run all jobs
    completed = 0
    failed = 0

    for date_obj, hour in jobs:
        success = run_combine_and_upload(date_obj, hour)
        if success:
            completed += 1
        else:
            failed += 1
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Completed: {completed}/{len(jobs)}")
    if failed > 0:
        print(f"Failed:    {failed}/{len(jobs)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
