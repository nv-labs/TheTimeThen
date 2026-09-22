"""
batch_extract_historical_photos.py

Runs auto_extract_historical_photos.py, one video after another, for every
video file found in a given input folder.

Usage:
    python batch_extract_historical_photos.py <folder_path>

Example:
    python batch_extract_historical_photos.py "D:\\Videos\\ToProcess"

Each video in the folder is processed sequentially (not in parallel) by
invoking:
    python auto_extract_historical_photos.py <video_path>
as a subprocess, exactly the same way it would be run manually for a single
video. All extraction, duplicate-checking, text writing, and the automatic
rewrite_extracted_text post-processing step happen exactly as they do today
for a single video -- this script just loops over every video in the folder.

A summary (processed / failed / skipped) is printed at the end.
"""

import os
import sys
import subprocess

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_SCRIPT = os.path.join(SCRIPT_DIR, "auto_extract_historical_photos.py")


def find_videos(folder):
    """Return a sorted list of video file paths directly inside `folder`."""
    videos = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and name.lower().endswith(VIDEO_EXTENSIONS):
            videos.append(path)
    return videos


def main():
    if len(sys.argv) < 2:
        print("Usage: python batch_extract_historical_photos.py <folder_path>")
        sys.exit(1)

    folder = sys.argv[1]
    if not os.path.isdir(folder):
        print(f"Error: Folder not found: {folder}")
        sys.exit(1)

    if not os.path.isfile(TARGET_SCRIPT):
        print(f"Error: Could not find {TARGET_SCRIPT}")
        sys.exit(1)

    videos = find_videos(folder)
    if not videos:
        print(f"No video files found in {folder} (looked for {', '.join(VIDEO_EXTENSIONS)})")
        sys.exit(0)

    print(f"Found {len(videos)} video(s) in {folder}. Processing one after another...\n")

    succeeded = []
    failed = []

    for i, video_path in enumerate(videos, start=1):
        print("=" * 70)
        print(f"[{i}/{len(videos)}] Processing: {os.path.basename(video_path)}")
        print("=" * 70)

        result = subprocess.run(
            [sys.executable, TARGET_SCRIPT, video_path],
        )

        if result.returncode == 0:
            succeeded.append(video_path)
            print(f"\n✅ Finished: {os.path.basename(video_path)}\n")
        else:
            failed.append(video_path)
            print(
                f"\n⚠️ Failed (exit code {result.returncode}): "
                f"{os.path.basename(video_path)}\n"
            )

    print("=" * 70)
    print("🎉 BATCH DONE")
    print(f"  Succeeded: {len(succeeded)}")
    for v in succeeded:
        print(f"    ✅ {os.path.basename(v)}")
    if failed:
        print(f"  Failed: {len(failed)}")
        for v in failed:
            print(f"    ⚠️ {os.path.basename(v)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
