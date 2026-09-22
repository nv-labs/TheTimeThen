"""
restyle_video_captions.py

Detects the burned-in caption text already present in a video (e.g. a
downloaded compilation video with italic/gold/serif captions) and re-renders
the video with the captions restyled to match the look used by
combine_dbs_slideshow.py (plain white, non-italic sans-serif text on a solid
black bar, centered at the bottom of the frame) -- i.e. the style seen in
combined_slideshow.mp4.

How it works:
  1. Samples the input video at a fixed interval and OCRs the bottom caption
     region of each sample (reusing the same OCR pipeline as
     auto_extract_centered_historical_photos.py: ocr_caption()).
  2. Groups consecutive samples with matching/similar text into caption
     "segments" (start_time, end_time, text), filtering out very short-lived
     noise/transition segments.
  3. Re-encodes the video with ffmpeg:
       - A solid black box is drawn over the entire caption region for the
         full duration (hides the original burned-in text).
       - For each detected segment, new text is drawn on top in the
         combine_dbs_slideshow.py style (white, Arial, centered, wrapped).
     Audio is copied through unchanged.

This is a best-effort OCR-based re-caption tool: OCR errors in noisy source
video captions may carry over into the restyled captions, so spot check the
output. Original file is left untouched; a new "<name>_restyled.mp4" file is
written next to it.

Usage:
    python restyle_video_captions.py "path\\to\\TTT20260825.mp4"
    python restyle_video_captions.py "path\\to\\TTT20260825.mp4" --sample-interval 1.5 --min-segment-sec 2.0
"""
import argparse
import os
import re
import sys
import textwrap
from collections import Counter
from difflib import SequenceMatcher

import cv2

import auto_extract_centered_historical_photos as base

FFMPEG_PATH = base.FFMPEG_PATH
FONT_PATH = r"C:\Windows\Fonts\arial.ttf"
DEFAULT_SAMPLE_INTERVAL = 1.0
DEFAULT_MIN_SEGMENT_SEC = 2.0
SIMILARITY_THRESHOLD = 0.55  # ratio above which two captions are treated as "the same"


def sample_captions(video_path, sample_interval, max_seconds=None):
    """OCR the caption region at regular intervals; return [(time_sec, text), ...]."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps > 0 else 0.0

    step_frames = max(1, int(round(sample_interval * fps)))
    samples = []

    frame_idx = 0
    while True:
        if max_seconds is not None and (frame_idx / fps) > max_seconds:
            break
        ok = cap.grab()
        if not ok:
            break
        if frame_idx % step_frames == 0:
            ok2, frame = cap.retrieve()
            if ok2 and frame is not None:
                t = frame_idx / fps
                text = base.ocr_caption(frame)
                samples.append((t, text))
                print(f"  [OCR] t={t:6.1f}s -> {text[:70]!r}")
        frame_idx += 1

    cap.release()
    return samples, duration


def _similar(a, b):
    if not a or not b:
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= SIMILARITY_THRESHOLD


def _extract_stable_core(texts):
    """Find the text that is stable across repeated OCR samples of the same caption.

    A real burned-in caption stays the same across frames while OCR noise
    (from a moving/blurred background behind the text) varies frame to
    frame. Progressively intersecting each sample with a running "core"
    string via longest-common-substring converges on the real, stable
    caption text and drops the noise around it.

    Because a couple of outlier OCR misreads near the very end of the
    caption can make the shared substring shorter than the true caption
    (e.g. dropping a trailing "1955."), a majority-vote pass then tries to
    recover a commonly-agreed-upon suffix that follows the core in most
    of the individual samples.
    """
    if not texts:
        return ""
    core = texts[0]
    for t in texts[1:]:
        matcher = SequenceMatcher(None, core, t)
        match = matcher.find_longest_match(0, len(core), 0, len(t))
        if match.size < 6:
            continue  # this sample looks unrelated/too noisy; skip it, keep prior core
        core = core[match.a: match.a + match.size]
    core = core.strip(" -_.,;:|\"'")
    if not core:
        return core

    # Majority-vote recovery of a trailing suffix that got trimmed by outliers.
    suffix_counts = Counter()
    for t in texts:
        idx = t.find(core)
        if idx == -1:
            continue
        tail = t[idx + len(core): idx + len(core) + 12].rstrip()
        # Keep only a clean leading token/punctuation run (avoid re-adding noise).
        m = re.match(r"^[\s.,]*([A-Za-z0-9][A-Za-z0-9 .,'\-]*)", tail)
        if m and m.group(1):
            suffix_counts[m.group(1).strip()] += 1

    if suffix_counts:
        best_suffix, count = suffix_counts.most_common(1)[0]
        if count >= max(2, len(texts) // 2) and best_suffix:
            core = f"{core} {best_suffix}".strip()

    return core


def flush_segment(current_texts, current_start, end_time, segments):
    if not current_texts:
        return
    core = _extract_stable_core(current_texts)
    # Fall back to the single best-scoring sample if the stable core turned out
    # too short to be a real caption (e.g. every sample was noisy/unrelated).
    candidate = core if len(core) >= 12 else max(current_texts, key=base.caption_text_score)
    if candidate and base.caption_text_score(candidate) >= 2.0:
        segments.append((current_start, end_time, candidate))


def build_segments(samples, min_segment_sec, sample_interval):
    """Group consecutive (time, text) samples into (start, end, text) segments."""
    segments = []
    current_texts = []
    current_start = None
    last_time = None

    for t, text in samples:
        if not text:
            # Blank/transition sample: close out current segment if any.
            if current_texts:
                flush_segment(current_texts, current_start, last_time + sample_interval if last_time is not None else t, segments)
                current_texts = []
                current_start = None
            last_time = t
            continue

        if not current_texts:
            current_texts = [text]
            current_start = t
        elif any(_similar(text, existing) for existing in current_texts[-3:]):
            current_texts.append(text)
        else:
            flush_segment(current_texts, current_start, t, segments)
            current_texts = [text]
            current_start = t
        last_time = t

    if current_texts and last_time is not None:
        flush_segment(current_texts, current_start, last_time + sample_interval, segments)

    # Drop segments that are too short to be a real caption (likely OCR noise).
    return [s for s in segments if (s[1] - s[0]) >= min_segment_sec]


def wrap_caption(text, width_px, font_size):
    # Roughly matches combine_dbs_slideshow.py's wrap-at-80-chars-for-1920px-wide logic,
    # scaled down proportionally for the target video's width.
    chars_per_line = max(10, int(80 * (width_px / 1920.0) * (42.0 / max(font_size, 1))))
    return "\n".join(textwrap.wrap(text, chars_per_line)) or text


def escape_ffmpeg_path(path):
    # ffmpeg filtergraph option values need ':' and '\' escaped.
    return path.replace("\\", "/").replace(":", "\\:")


def render_restyled_video(video_path, segments, duration, width, height, output_path, tmp_dir):
    os.makedirs(tmp_dir, exist_ok=True)

    font_size = max(12, int(round(42 * (width / 1920.0))))
    bar_y_px = int(round(height * 0.68))  # matches auto_extract_centered_historical_photos.crop_caption_region
    bar_h_px = height - bar_y_px

    filters = [
        f"drawbox=x=0:y={bar_y_px}:w={width}:h={bar_h_px}:color=black@1.0:t=fill"
    ]

    for i, (start, end, text) in enumerate(segments):
        wrapped = wrap_caption(text, width, font_size)
        txt_path = os.path.join(tmp_dir, f"caption_{i:04d}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(wrapped)
        textfile_arg = escape_ffmpeg_path(os.path.abspath(txt_path))
        fontfile_arg = escape_ffmpeg_path(FONT_PATH)
        filters.append(
            "drawtext="
            f"fontfile='{fontfile_arg}':"
            f"textfile='{textfile_arg}':"
            "fontcolor=white:"
            f"fontsize={font_size}:"
            "line_spacing=4:"
            "x=(w-text_w)/2:"
            f"y={bar_y_px}+({bar_h_px}-text_h)/2:"
            f"enable='between(t,{start:.2f},{end:.2f})'"
        )

    filter_complex = ",".join(filters)

    cmd = [
        FFMPEG_PATH, "-y",
        "-i", video_path,
        "-vf", filter_complex,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "copy",
        output_path,
    ]
    print(f"[FFMPEG] rendering {len(segments)} caption segment(s) -> {output_path}")
    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-4000:])
        raise RuntimeError("ffmpeg render failed")


def main():
    parser = argparse.ArgumentParser(
        description="Re-caption a video's burned-in text using the plain white "
                    "non-italic style from combine_dbs_slideshow.py."
    )
    parser.add_argument("video", help="Path to the source video (e.g. TTT20260825.mp4)")
    parser.add_argument("--sample-interval", type=float, default=DEFAULT_SAMPLE_INTERVAL,
                         help="Seconds between OCR samples (default: 1.0)")
    parser.add_argument("--min-segment-sec", type=float, default=DEFAULT_MIN_SEGMENT_SEC,
                         help="Minimum caption duration to keep, filters OCR noise (default: 2.0)")
    parser.add_argument("--output", default=None, help="Output path (default: <name>_restyled.mp4 next to input)")
    parser.add_argument("--max-seconds", type=float, default=None,
                         help="Only process the first N seconds (useful for a quick test)")
    args = parser.parse_args()

    if not os.path.isfile(args.video):
        print(f"Error: file not found: {args.video}")
        sys.exit(1)

    cap = cv2.VideoCapture(args.video)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    print(f"[INFO] video: {args.video} ({width}x{height})")
    print("[INFO] sampling captions via OCR...")
    samples, duration = sample_captions(args.video, args.sample_interval, max_seconds=args.max_seconds)

    if args.max_seconds:
        samples = [s for s in samples if s[0] <= args.max_seconds]
        duration = min(duration, args.max_seconds)

    print(f"[INFO] {len(samples)} OCR sample(s) over {duration:.1f}s")

    segments = build_segments(samples, args.min_segment_sec, args.sample_interval)
    print(f"[INFO] detected {len(segments)} caption segment(s):")
    for start, end, text in segments:
        print(f"  {start:7.1f}s - {end:7.1f}s | {text}")

    if not segments:
        print("[WARN] no caption segments detected; nothing to restyle.")
        sys.exit(1)

    output_path = args.output
    if not output_path:
        base_name, ext = os.path.splitext(args.video)
        output_path = f"{base_name}_restyled{ext}"

    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(args.video)), "_restyle_tmp")

    if args.max_seconds:
        # For a quick test, trim the source first so ffmpeg only re-encodes the tested range.
        trimmed_path = os.path.join(tmp_dir, "trimmed_input.mp4")
        os.makedirs(tmp_dir, exist_ok=True)
        import subprocess
        subprocess.run(
            [FFMPEG_PATH, "-y", "-i", args.video, "-t", str(args.max_seconds),
             "-c", "copy", trimmed_path],
            capture_output=True, text=True, check=True,
        )
        render_restyled_video(trimmed_path, segments, duration, width, height, output_path, tmp_dir)
    else:
        render_restyled_video(args.video, segments, duration, width, height, output_path, tmp_dir)

    print(f"[DONE] restyled video written to: {output_path}")


if __name__ == "__main__":
    main()
