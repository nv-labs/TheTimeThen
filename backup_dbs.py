#!/usr/bin/env python3
"""
Automatic weekly database backup with date-stamped files and cleanup.

Features:
  - Backs up DB files with date extension (e.g., filename.db.20260615)
  - Checks if drive F: is available daily (at startup)
  - Only runs once per week (if already ran this week, waits until next week)
  - Automatically deletes old backups after 1 month (keeps only latest of each month)

Usage:
  python backup_dbs.py                 # Run now if conditions met
  python backup_dbs.py --force         # Force backup regardless of schedule
  python backup_dbs.py --setup-task    # Setup Windows Task Scheduler (runs at startup)
"""

import shutil
import os
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

SOURCE_DIR = r"D:\Dev\TheTimeThen"
BACKUP_DIR = r"F:\TheTimeThen\Backup"
STATE_FILE = os.path.join(SOURCE_DIR, ".backup_state.json")

DB_FILES = [
    "google_takeout_photos_2023.db",
    "image_collection.db",
    "universal_image_archive.db"
]


def load_state():
    """Load backup state (last backup timestamp)."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_state(state):
    """Save backup state."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save state file: {e}")


def is_drive_available():
    """Check if F: drive is available."""
    return os.path.exists(r"F:\TheTimeThen\Backup") or os.path.exists("F:\\")


def should_run_backup(force=False):
    """Check if backup should run this week."""
    if force:
        return True, "Forced backup"
    
    if not is_drive_available():
        return False, "Drive F: not available"
    
    state = load_state()
    last_backup_str = state.get("last_backup")
    
    if not last_backup_str:
        return True, "First backup"
    
    try:
        last_backup = datetime.fromisoformat(last_backup_str)
        now = datetime.now()
        days_since = (now - last_backup).days
        
        if days_since < 7:
            days_remaining = 7 - days_since
            return False, f"Already backed up this week ({days_remaining} days remaining)"
        else:
            return True, "One week has passed since last backup"
    except:
        return True, "Could not parse last backup time"


def ensure_backup_dir_exists():
    """Create backup directory if it doesn't exist."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)


def cleanup_old_backups():
    """Keep only the latest backup per month after 1 month has passed."""
    if not os.path.exists(BACKUP_DIR):
        return
    
    # Group backups by filename and month
    backups_by_file = defaultdict(list)
    
    for filename in os.listdir(BACKUP_DIR):
        filepath = os.path.join(BACKUP_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        
        # Parse: filename.db.YYYYMMDD
        if '.' in filename:
            parts = filename.rsplit('.', 1)
            if len(parts) == 2 and len(parts[1]) == 8 and parts[1].isdigit():
                base_name = parts[0]
                date_str = parts[1]
                try:
                    backup_date = datetime.strptime(date_str, "%Y%m%d")
                    backups_by_file[base_name].append((backup_date, filepath, date_str))
                except:
                    pass
    
    now = datetime.now()
    one_month_ago = now - timedelta(days=30)
    deleted_count = 0
    
    for base_name, backups in backups_by_file.items():
        # Group by month
        by_month = defaultdict(list)
        for backup_date, filepath, date_str in backups:
            month_key = backup_date.strftime("%Y-%m")
            by_month[month_key].append((backup_date, filepath, date_str))
        
        # For months older than 1 month, keep only latest
        for month_key, month_backups in by_month.items():
            month_backups.sort(reverse=True)
            month_date = datetime.strptime(month_key, "%Y-%m")
            
            if month_date < one_month_ago:
                # Keep the latest, delete the rest
                for backup_date, filepath, date_str in month_backups[1:]:
                    try:
                        os.remove(filepath)
                        print(f"   Deleted old backup: {os.path.basename(filepath)}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"   Warning: Could not delete {os.path.basename(filepath)}: {e}")
    
    if deleted_count > 0:
        print(f"\nCleanup: Removed {deleted_count} old backup(s)")


def copy_dbs(force=False):
    """Copy all DB files from source to backup with date extension."""
    should_run, reason = should_run_backup(force)
    
    print("=" * 70)
    print("DATABASE BACKUP")
    print("=" * 70)
    print(f"Source:     {SOURCE_DIR}")
    print(f"Backup to:  {BACKUP_DIR}")
    print(f"Reason:     {reason}")
    print("=" * 70)
    print()
    
    if not should_run:
        print(f"⊘ SKIPPED: {reason}\n")
        return False
    
    ensure_backup_dir_exists()
    
    date_ext = datetime.now().strftime("%Y%m%d")
    copied = 0
    failed = 0
    skipped = 0
    
    for db_file in DB_FILES:
        source_path = os.path.join(SOURCE_DIR, db_file)
        backup_path = os.path.join(BACKUP_DIR, f"{db_file}.{date_ext}")
        
        if not os.path.exists(source_path):
            print(f"⊘ SKIPPED: {db_file} (not found in source)")
            skipped += 1
            continue
        
        try:
            file_size_mb = os.path.getsize(source_path) / (1024 * 1024)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] ► Copying {db_file} ({file_size_mb:.2f} MB)...", end=" ", flush=True)
            
            shutil.copy2(source_path, backup_path)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"✓")
            copied += 1
            
        except Exception as e:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"✗\n     Error: {e}")
            failed += 1
    
    if copied > 0:
        state = load_state()
        state["last_backup"] = datetime.now().isoformat()
        save_state(state)
    
    # Clean up old backups
    print()
    cleanup_old_backups()
    
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Copied:  {copied}")
    print(f"Failed:  {failed}")
    print(f"Skipped: {skipped}")
    print("=" * 70)
    
    return copied > 0


def setup_task():
    """Setup Windows Task Scheduler to run at startup."""
    print("Setting up Windows Task Scheduler...")
    
    script_path = os.path.abspath(__file__)
    task_name = "BackupTheTimeThenDBs"
    task_description = "Weekly backup of TheTimeThen database files"
    
    # PowerShell command to create the task
    ps_cmd = f'''
$action = New-ScheduledTaskAction -Execute "python.exe" -Argument '"{script_path}"'
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName "{task_name}" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "{task_description}" -Force
Write-Host "Task '{task_name}' created successfully!"
'''
    
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            check=True,
            capture_output=True
        )
        print(f"✓ Task '{task_name}' created successfully!")
        print(f"  The backup will run automatically at startup.")
    except subprocess.CalledProcessError as e:
        print(f"✗ Error creating task: {e}")
        print(f"  Try running as Administrator")
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Automatic weekly backup of TheTimeThen database files",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force backup regardless of schedule"
    )
    parser.add_argument(
        "--setup-task",
        action="store_true",
        help="Setup Windows Task Scheduler to run at startup"
    )
    
    args = parser.parse_args()
    
    if args.setup_task:
        setup_task()
    else:
        copy_dbs(force=args.force)


if __name__ == "__main__":
    main()
