#!/usr/bin/env python3
r"""
Batch runner using DBs stored under F:\TheTimeThen\Backup.
Usage:
    python schedule_bulk_uploads_backup.py 2026-04-03
Options:
    --use-universal   Use universal_image_archive.db as the second DB instead of image_collection.db

This mirrors schedule_bulk_uploads.py but points to the backup DB locations.
"""

import subprocess
import argparse
from datetime import datetime, timedelta
import os

# Backup directory and DB paths
BACKUP_DIR = r"F:\TheTimeThen\Backup"
DB_IMAGE_COLLECTION = os.path.join(BACKUP_DIR, "image_collection.db")
DB_UNIVERSAL_ARCHIVE = os.path.join(BACKUP_DIR, "universal_image_archive.db")
DB_GOOGLE_TAKEOUT = os.path.join(BACKUP_DIR, "google_takeout_photos_2023.db")


def run_combine_and_upload(date_obj, hour, db1, db2):
    """Run combine_and_upload.py with the specified DBs and outdir."""

    date_str = date_obj.strftime("%Y%m%d")
    month_str = date_obj.strftime("%m")
    hour_str = f"{hour:02d}h"
    outdir = f"D:\\Youtube\\TTT\\2026\\{month_str}\\{date_str}-{hour_str}"
    
    air_date_str = f"{date_obj.strftime('%Y-%m-%d')} {hour:02d}:00:00"

    python_exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "autos", "Scripts", "python.exe")

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
    print(f"   Using DBs:\n     db1: {db1}\n     db2: {db2}")
    print(f"   Output: {outdir}")

    try:
        result = subprocess.run(cmd, check=True, cwd=os.path.dirname(os.path.abspath(__file__)))
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] ✓ Completed!")
        return True
    except subprocess.CalledProcessError as e:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] ✗ Error: Exit code {e.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run combine_and_upload.py for multiple dates using backup DBs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("start_date", help="Start date in format YYYY-MM-DD (e.g., 2026-04-03)")
    parser.add_argument("--one-day", action="store_true", help="Only process the start date (1 run)")
    parser.add_argument("--use-universal", action="store_true", help="Use universal_image_archive.db as db2 instead of image_collection.db")

    args = parser.parse_args()

    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    except ValueError:
        print("❌ Invalid date format. Please use YYYY-MM-DD (e.g., 2026-04-03)")
        return

    jobs = []
    if args.one_day:
        jobs.append((start_date, 23))
        duration_str = "1 day (1 total run)"
    else:
        for day_offset in range(10):
            current_date = start_date + timedelta(days=day_offset)
            jobs.append((current_date, 23))
        duration_str = "10 days (10 total runs)"

    db1 = DB_GOOGLE_TAKEOUT
    db2 = DB_UNIVERSAL_ARCHIVE if args.use_universal else DB_IMAGE_COLLECTION

    print("=" * 70)
    print("BATCH RUNNER: combine_and_upload.py (backup DBs)")
    print("=" * 70)
    print(f"Start Date: {start_date.strftime('%Y-%m-%d')}")
    print(f"Duration: {duration_str}")
    print(f"Backup dir: {BACKUP_DIR}")
    print("\nExecution Plan:")
    print("-" * 70)

    for date_obj, hour in jobs:
        print(f"  {date_obj.strftime('%Y-%m-%d')} {hour:02d}h")

    print("-" * 70)
    print(f"Total: {len(jobs)} executions\n")

    completed = 0
    failed = 0

    for date_obj, hour in jobs:
        success = run_combine_and_upload(date_obj, hour, db1, db2)
        if success:
            completed += 1
        else:
            failed += 1

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Completed: {completed}/{len(jobs)}")
    if failed > 0:
        print(f"Failed:    {failed}/{len(jobs)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
