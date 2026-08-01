import argparse
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

TASK_NAME = "TheTimeThenDailyDbBackup"
BACKUP_ROOT = Path(r"F:\TheTimeThen\DataBaseTTT-Bu")
SOURCE_DIR = Path(r"D:\Dev\TheTimeThen")
DB_FILES = [
    "google_takeout_photos_2023.db",
    "image_collection.db",
    "universal_image_archive.db",
    "mydb.db",
]

STATE_FILE = BACKUP_ROOT / "backup_state.json"
LOG_FILE = BACKUP_ROOT / "backup.log"
DAILY_DIR = BACKUP_ROOT / "daily"
MONTHLY_DIR = BACKUP_ROOT / "monthly"


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def wait_for_backup_drive(timeout_seconds: int = 180, interval_seconds: int = 5) -> bool:
    end_time = time.time() + timeout_seconds
    while time.time() < end_time:
        if BACKUP_ROOT.drive and Path(BACKUP_ROOT.drive + "\\").exists():
            return True
        time.sleep(interval_seconds)
    return False


def sqlite_consistent_backup(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_suffix(dst.suffix + ".tmp")

    for stale in (tmp_dst, Path(str(tmp_dst) + "-journal")):
        if stale.exists():
            stale.unlink()

    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(tmp_dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()

        tmp_dst.replace(dst)
    except Exception:
        for stale in (tmp_dst, Path(str(tmp_dst) + "-journal")):
            if stale.exists():
                stale.unlink()
        raise
    finally:
        src_conn.close()


def do_backups(force: bool = False) -> int:
    if not wait_for_backup_drive():
        log(f"Backup drive not available: {BACKUP_ROOT.drive}")
        return 2

    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)

    state = load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    month_key = datetime.now().strftime("%Y-%m")

    if not force and state.get("last_daily_run") == today:
        log("Backup already ran today; skipping.")
        return 0

    monthly_target = MONTHLY_DIR / month_key
    monthly_target.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for db_name in DB_FILES:
        src = SOURCE_DIR / db_name
        if not src.exists():
            log(f"SKIP missing source: {src}")
            continue

        # Cleanup leftovers from interrupted previous runs.
        for stale in (
            DAILY_DIR / f"{db_name}.tmp",
            DAILY_DIR / f"{db_name}.tmp-journal",
            monthly_target / f"{db_name}.tmp",
            monthly_target / f"{db_name}.tmp-journal",
        ):
            if stale.exists():
                stale.unlink()

        daily_dst = DAILY_DIR / db_name
        try:
            sqlite_consistent_backup(src, daily_dst)
            log(f"OK daily overwrite: {daily_dst}")
        except Exception as exc:
            log(f"ERROR daily backup failed for {src}: {exc}")
            continue

        monthly_dst = monthly_target / db_name
        if monthly_dst.exists():
            log(f"KEEP monthly existing: {monthly_dst}")
        else:
            try:
                sqlite_consistent_backup(src, monthly_dst)
                log(f"OK monthly snapshot: {monthly_dst}")
            except Exception as exc:
                log(f"ERROR monthly backup failed for {src}: {exc}")
                continue

        success_count += 1

    state["last_daily_run"] = today
    state["last_month_key"] = month_key
    save_state(state)

    log(f"Finished backup run. Databases completed: {success_count}/{len(DB_FILES)}")
    return 0 if success_count > 0 else 1


def install_startup_task() -> int:
    script_path = Path(__file__).resolve()
    python_exe = Path(sys.executable).resolve()

    # Runs on startup; script itself enforces once-per-day behavior.
    task_command = f'"{python_exe}" "{script_path}"'
    cmd = [
        "schtasks",
        "/Create",
        "/F",
        "/TN",
        TASK_NAME,
        "/SC",
        "ONSTART",
        "/RL",
        "HIGHEST",
        "/TR",
        task_command,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Failed to create task '{TASK_NAME}': {result.stderr.strip()}")
        return result.returncode

    log(f"Scheduled task created: {TASK_NAME}")
    return 0


def remove_startup_task() -> int:
    cmd = ["schtasks", "/Delete", "/F", "/TN", TASK_NAME]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Failed to delete task '{TASK_NAME}': {result.stderr.strip()}")
        return result.returncode

    log(f"Scheduled task deleted: {TASK_NAME}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Daily SQLite backup with overwrite + monthly snapshots.",
    )
    parser.add_argument("--force", action="store_true", help="Run backup even if it already ran today.")
    parser.add_argument(
        "--install-task",
        action="store_true",
        help="Install Windows startup scheduled task for automatic backup.",
    )
    parser.add_argument(
        "--remove-task",
        action="store_true",
        help="Remove the Windows startup scheduled task.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.install_task:
        return install_startup_task()

    if args.remove_task:
        return remove_startup_task()

    return do_backups(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
