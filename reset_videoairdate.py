#!/usr/bin/env python3
"""
Reset VideoAirDate to NULL for images used in the last run of combine_dbs_slideshow.

By default the script will look for an output video file `combined_slideshow.mp4`
in the provided output directory (or current dir) and use its modification time to
identify recent `VideoAirDate` values within a small time window.

Usage examples:
  python reset_videoairdate.py --db1 d:/Dev/TheTimeThen/universal_image_archive.db --db1-table photos_2023_photos --db2 d:/Dev/TheTimeThen/image_collection.db --db2-table image_comp --outdir out

Options:
  --window SECONDS   Time window (seconds) around video mtime to consider (default 30)
  --dry-run          Don't modify DBs; just report which rows would be reset
  --timestamp TS      Use this exact timestamp (YYYY-MM-DD HH:MM:SS) instead of video mtime
"""
import argparse
import os
import sqlite3
from datetime import datetime, timedelta


def parse_ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def find_recent_ids(db, table, window_start, window_end):
    if not os.path.exists(db):
        return []
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    try:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        if 'VideoAirDate' not in cols:
            conn.close()
            return []
    except Exception:
        conn.close()
        return []

    cur.execute(f"SELECT id, VideoAirDate FROM {table} WHERE VideoAirDate IS NOT NULL AND VideoAirDate != ''")
    rows = cur.fetchall()
    conn.close()

    ids = []
    for pid, ts in rows:
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except Exception:
            # skip unparsable formats
            continue
        if window_start <= dt <= window_end:
            ids.append(pid)
    return ids


def reset_ids(db, table, ids, dry_run=False):
    if not ids:
        return 0
    if dry_run:
        return len(ids)
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.executemany(f"UPDATE {table} SET VideoAirDate = NULL WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    conn.close()
    return len(ids)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db1", required=True)
    p.add_argument("--db1-table", default="photos_2023_photos")
    p.add_argument("--db2", required=True)
    p.add_argument("--db2-table", default="image_comp")
    p.add_argument("--outdir", default=".")
    p.add_argument("--window", type=int, default=30)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--timestamp", default=None, help="Optional exact timestamp to target (YYYY-MM-DD HH:MM:SS)")
    args = p.parse_args()

    video_path = os.path.join(args.outdir, "combined_slideshow.mp4")
    if args.timestamp:
        ts = parse_ts(args.timestamp)
        if not ts:
            print("Invalid timestamp format. Use 'YYYY-MM-DD HH:MM:SS'")
            return
    else:
        if not os.path.exists(video_path):
            print(f"Video not found at {video_path}. Provide --timestamp or ensure the video exists.")
            return
        mtime = os.path.getmtime(video_path)
        ts = datetime.fromtimestamp(mtime)

    window = timedelta(seconds=args.window)
    start = ts - window
    end = ts + window

    print(f"Target window: {start} -> {end}")

    ids1 = find_recent_ids(args.db1, args.db1_table, start, end)
    ids2 = find_recent_ids(args.db2, args.db2_table, start, end)

    print(f"DB1 ({args.db1_table}) candidate ids to reset: {ids1}")
    print(f"DB2 ({args.db2_table}) candidate ids to reset: {ids2}")

    if args.dry_run:
        print("Dry-run: no changes made.")
    else:
        n1 = reset_ids(args.db1, args.db1_table, ids1, dry_run=False)
        n2 = reset_ids(args.db2, args.db2_table, ids2, dry_run=False)
        print(f"Reset {n1} rows in db1 and {n2} rows in db2.")


if __name__ == '__main__':
    main()
