#!/usr/bin/env python3
r"""
Run combine_and_upload.py multiple times with correct output directories.

Usage:
    python schedule_bulk_uploads.py 2026-04-03 23h
    python schedule_bulk_uploads.py 2026-04-03 23h,14h

This will run the script 10 times immediately (10 days × 1 time per day
at the hour you pass as the second argument, e.g. 23h):
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

If you pass multiple comma-separated hours (e.g. 23h,14h), each day gets
one run per hour listed, for example:
    - 2026-04-03: 23h
    - 2026-04-03: 14h
    - 2026-04-04: 23h
    - 2026-04-04: 14h
    ... (10 days × 2 runs per day = 20 total runs)

Each run uses the outdir format: D:\Youtube\TTT\2026\MM\YYYYMMdd-HHh
"""

import subprocess
import argparse
from datetime import datetime, timedelta
import os

DEFAULT_PLAYLIST_PREFIX = "Historical Old Photos.."
DEFAULT_AUTO_IMPORT_END_SCREEN = "1"
DB_DIR = r"D:\Nvisions OneDrive\OneDrive\TheTimeThen-Data\databases"
DB_GOOGLE_TAKEOUT = os.path.join(DB_DIR, "google_takeout_photos_2023.db")
DB_IMAGE_COLLECTION = os.path.join(DB_DIR, "image_collection.db")

def parse_hour_arg(hour_str):
    value = str(hour_str).strip().lower()
    if value.endswith("h"):
        value = value[:-1]
    if not value.isdigit():
        raise ValueError("Hour must be in format HH or HHh (e.g., 14 or 14h)")
    hour = int(value)
    if hour < 0 or hour > 23:
        raise ValueError("Hour must be between 0 and 23")
    return hour


def parse_hours_arg(hours_str):
    """Parse one or more comma-separated hours, e.g. '23h' or '23h,14h'."""
    parts = [p.strip() for p in str(hours_str).split(",") if p.strip()]
    if not parts:
        raise ValueError("At least one hour must be provided")
    hours = [parse_hour_arg(p) for p in parts]
    # De-duplicate while preserving order
    seen = set()
    unique_hours = []
    for h in hours:
        if h not in seen:
            seen.add(h)
            unique_hours.append(h)
    return unique_hours


def run_combine_and_upload(date_obj, hour, db1, db2):
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
        "--db1", db1,
        "--db1-table", "photos",
        "--db2", db2,
        "--db2-table", "image_comp",
        "--n1", "10",
        "--n2", "25",
        "--outdir", outdir,
        "--air-date", air_date_str
    ]
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[{timestamp}] ► Running for {date_obj.strftime('%Y-%m-%d')} {hour:02d}h")
    print(f"   Using DBs: {db1} and {db2}")
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
        description="Run combine_and_upload.py for multiple days at one or more scheduled hours per day",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python schedule_bulk_uploads.py 2026-04-03 23h
  python schedule_bulk_uploads.py 2026-03-28 14h
  python schedule_bulk_uploads.py 2026-04-03 14h --one-day
  python schedule_bulk_uploads.py 2026-04-03 23h,14h
  python schedule_bulk_uploads.py 2026-04-03 23h,14h --one-day
        """
    )
    parser.add_argument(
        "start_date",
        help="Start date in format YYYY-MM-DD (e.g., 2026-04-03)"
    )
    parser.add_argument(
        "hour",
        help="YouTube schedule hour(s) in format HHh or HH, comma-separated for multiple (e.g., 14h or 23h,14h)"
    )
    parser.add_argument(
        "--one-day",
        action="store_true",
        help="Only process the start date (1 video per hour specified, at the specified hour(s))"
    )

    args = parser.parse_args()

    # Parse the start date
    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    except ValueError:
        print("❌ Invalid date format. Please use YYYY-MM-DD (e.g., 2026-04-03)")
        return
    try:
        schedule_hours = parse_hours_arg(args.hour)
    except ValueError as e:
        print(f"❌ Invalid hour: {e}")
        return

    # Build all jobs
    jobs = []
    if args.one_day:
        for hour in schedule_hours:
            jobs.append((start_date, hour))
        duration_str = f"1 day ({len(schedule_hours)} total run(s))"
    else:
        for day_offset in range(10):
            current_date = start_date + timedelta(days=day_offset)
            for hour in schedule_hours:
                jobs.append((current_date, hour))
        duration_str = f"10 days ({len(jobs)} total runs)"

    # Display the plan
    print("=" * 70)
    print("BATCH RUNNER: combine_and_upload.py")
    print("=" * 70)
    print(f"Start Date: {start_date.strftime('%Y-%m-%d')}")
    print(f"Scheduled Hour(s): {', '.join(f'{h:02d}h' for h in schedule_hours)}")
    print(f"Duration: {duration_str}")
    print(f"Playlist prefix: {os.environ.get('YT_PLAYLIST_TITLE_PREFIX', DEFAULT_PLAYLIST_PREFIX)}")
    print(f"Auto end screen import: {os.environ.get('YT_AUTO_IMPORT_END_SCREEN', DEFAULT_AUTO_IMPORT_END_SCREEN)}")
    print(f"DB1 (Google Takeout): {DB_GOOGLE_TAKEOUT}")
    print(f"DB2 (Image Collection): {DB_IMAGE_COLLECTION}")
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
        success = run_combine_and_upload(date_obj, hour, DB_GOOGLE_TAKEOUT, DB_IMAGE_COLLECTION)
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
