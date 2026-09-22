"""
extract_and_enrich_photos.py

Inspired by auto_extract_centered_historical_photos.py, but instead of relying only
on OCR'd caption text, this script:

  1. Extracts a candidate photo from the source video at each anchor timestamp
     (reusing the same frame-selection / center-crop / OCR logic).
  2. Identifies the subject of the photo via **reverse image search** (Google
     Cloud Vision "Web Detection" -- searches the web using the actual image
     pixels, not OCR text) when a GOOGLE_VISION_API_KEY is configured. Falls
     back to an OCR-caption text search against Wikipedia (with strict
     relevance filtering) when no Vision API key is available.
  3. Downloads the best full-resolution image it can find: the exact matching
     image from the web (via Vision web detection) if available, otherwise
     the lead image from a matched Wikipedia article, otherwise the cropped
     video frame is kept as a last-resort fallback.
  4. Writes an "interesting info" description into output/extracted_text_cleaned.txt.

Why Google Cloud Vision instead of scraping a search engine directly?
  General-purpose search engines (Bing, DuckDuckGo, Google, Yandex) actively
  block scripted/automated queries and reverse-image uploads with anti-bot
  challenges. Bypassing that kind of bot-detection is not something this tool
  will do. Google Cloud Vision's Web Detection feature is the official,
  supported way to do this: you send image bytes, it returns pages/images
  matching the picture across the web, plus a "best guess" label. It has a
  free tier (1,000 images/month) but does require a Google Cloud project +
  API key -- see the SETUP note below.

SETUP (optional, enables true reverse-image search):
    1. Create a Google Cloud project and enable the "Cloud Vision API".
    2. Create an API key (APIs & Services > Credentials).
    3. Add it to TheTimeThen/.env as:  GOOGLE_VISION_API_KEY=your-key-here
  Without this key, the script still runs, but falls back to a stricter
  OCR-caption-based Wikipedia text search (lower hit rate, but won't report
  false matches like "Sirs" or "NAT" on garbage OCR text).

This is a best-effort heuristic pipeline: matches are not guaranteed to be the
exact photo/person, so always spot check results.

Usage (test with first 3 photos only):
    python extract_and_enrich_photos.py "path\\to\\video.mp4" --max-frames 3

Requires: requests, beautifulsoup4 (already used elsewhere in this project).
"""
import argparse
import base64
import os
import re
import sys
import time

import cv2
import requests
from bs4 import BeautifulSoup

# Reuse the proven frame-extraction / OCR / crop pipeline instead of duplicating it.
import auto_extract_centered_historical_photos as base

OUTPUT_DIR = base.OUTPUT_DIR
TEXT_FILE = "extracted_text_cleaned.txt"
ENRICHED_SUBDIR = "enriched"
TEMP_FRAME = base.TEMP_FRAME

WIKI_API = "https://en.wikipedia.org/w/api.php"
VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"
# Wikimedia asks bots to identify themselves with a descriptive UA; a generic
# one gets rate-limited (HTTP 429) more aggressively on upload.wikimedia.org.
USER_AGENT = (
    "TheTimeThenPhotoArchiveBot/1.0 "
    "(https://github.com/nv-labs/TheTimeThen; personal historical photo cataloging)"
)
REQUEST_TIMEOUT = 12
SEARCH_SLEEP_SEC = 1.0
DOWNLOAD_SLEEP_SEC = 1.5
DOWNLOAD_MAX_RETRIES = 3
MIN_FULLRES_BYTES = 25_000  # skip tiny/placeholder images
MIN_SHARED_TOKEN_LEN = 5  # relevance gate: query/title must share a token this long
# Generic words are too common to count as a meaningful identifying match on
# their own (e.g. matching only on "women" or "history" is not a real match).
GENERIC_STOPWORDS = {
    "women", "woman", "world", "history", "family", "people", "group",
    "american", "british", "africa", "company", "music", "international",
    "national", "university", "school", "state", "states", "united", "city",
    "football", "club", "sports", "society", "association", "movement",
    "government", "children", "young", "photo", "photos", "picture",
    "pictures", "image", "images", "party", "church", "college", "hospital",
}


def _read_dotenv_key(dotenv_path, key_name):
    """Minimal .env reader (same pattern used elsewhere in this project)."""
    if not os.path.exists(dotenv_path):
        return None
    try:
        with open(dotenv_path, "r", encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() != key_name:
                    continue
                value = v.strip().strip('"').strip("'")
                if value:
                    return value
    except Exception:
        return None
    return None


def resolve_vision_api_key():
    key = os.getenv("GOOGLE_VISION_API_KEY", "").strip()
    if key:
        return key
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return _read_dotenv_key(os.path.join(script_dir, ".env"), "GOOGLE_VISION_API_KEY")


def _alpha_tokens(text):
    return set(t.lower() for t in re.findall(r"[A-Za-z]+", text or ""))


def _is_relevant_match(query, title):
    """Relevance gate: require a shared, non-generic word between query and title.

    Wikipedia's full-text search will happily return a fuzzy/partial match for
    almost any input (e.g. garbage OCR token "Nats" matching "Network address
    translation"). To avoid reporting wrong facts, only accept a match if the
    query and the candidate title share at least one specific (non-generic)
    word of meaningful length.
    """
    query_tokens = {
        t for t in _alpha_tokens(query)
        if len(t) >= MIN_SHARED_TOKEN_LEN and t not in GENERIC_STOPWORDS
    }
    title_tokens = _alpha_tokens(title) - GENERIC_STOPWORDS
    return bool(query_tokens & title_tokens)


def clean_search_query(caption_text):
    """Extract a usable Wikipedia search query from noisy OCR caption text.

    OCR captions are full of garbage tokens (stray symbols read as random
    letters). The real signal in most captions is the proper nouns (people,
    places) written in Title Case, plus a year. So instead of keeping every
    word, we isolate the longest run of consecutive Title-Case words (e.g.
    "Rock Hudson", "Clark Gable") and append any 4-digit year found nearby.
    Only runs of >= 2 words are considered a real name/place candidate --
    single stray Title-Case words ("Sirs", "Eee") are too likely to be OCR
    noise and are rejected outright.
    """
    text = caption_text or ""
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", text)
    year_match = re.search(r"\b(18|19|20)\d{2}\b", cleaned)
    year = year_match.group(0) if year_match else ""

    tokens = cleaned.split()
    runs = []
    current_run = []
    for token in tokens:
        if re.match(r"^[A-Z][a-z]+$", token):
            current_run.append(token)
        else:
            if current_run:
                runs.append(current_run)
            current_run = []
    if current_run:
        runs.append(current_run)

    best_run = max(runs, key=len) if runs else []
    if len(best_run) < 2:
        return ""  # not enough signal to trust; avoid false-positive matches

    query = " ".join(best_run)
    if year:
        query = (query + " " + year).strip()
    return query.strip()


def clean_info_text(text, max_chars=400):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > max_chars:
        # Cut at the last sentence boundary before max_chars, if possible.
        cut = text[:max_chars]
        last_period = cut.rfind(". ")
        text = cut[: last_period + 1] if last_period > 80 else cut.rstrip() + "..."
    text = text.strip(" .,-|")
    if not text:
        return ""
    if not text.endswith((".", "...")):
        text += "."
    return text


def wikipedia_search(query, max_results=3):
    """Return a list of relevant Wikipedia article titles matching the query.

    Applies a relevance gate (_is_relevant_match) to filter out Wikipedia's
    fuzzy/partial matches that share no real words with the query.
    """
    if not query:
        return []
    try:
        resp = requests.get(
            WIKI_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": max_results,
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        titles = [item["title"] for item in data.get("query", {}).get("search", [])]
        relevant = [t for t in titles if _is_relevant_match(query, t)]
        if titles and not relevant:
            print(f"  [SEARCH] discarded irrelevant matches: {titles}")
        return relevant
    except Exception as e:
        print(f"  [WARN] Wikipedia search failed: {e}")
        return []


def fetch_page_description(url):
    """Best-effort scrape of a page's og:description / meta description."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for attrs in (
            {"property": "og:description"},
            {"name": "description"},
            {"name": "twitter:description"},
        ):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return tag["content"].strip()
    except Exception as e:
        print(f"  [WARN] page description fetch failed for {url}: {e}")
    return ""


def google_vision_web_detection(image_bytes, api_key):
    """Reverse image search via Google Cloud Vision Web Detection.

    Returns a dict with:
      best_guess: str or None            -- Vision's best-guess label for the image
      match_image_url: str or None       -- a full/partial matching image URL found on the web
      match_page_url: str or None        -- a page URL that contains a matching image
    or None if the request fails / no key configured.
    """
    if not api_key:
        return None
    try:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "requests": [
                {
                    "image": {"content": encoded},
                    "features": [{"type": "WEB_DETECTION", "maxResults": 10}],
                }
            ]
        }
        resp = requests.post(
            VISION_API_URL,
            params={"key": api_key},
            json=payload,
            timeout=REQUEST_TIMEOUT + 8,
        )
        resp.raise_for_status()
        data = resp.json()
        web = (data.get("responses") or [{}])[0].get("webDetection", {})

        best_guess = None
        labels = web.get("bestGuessLabels") or []
        if labels:
            best_guess = labels[0].get("label")

        match_image_url = None
        for key in ("fullMatchingImages", "pagesWithMatchingImages"):
            items = web.get(key) or []
            if items:
                if key == "fullMatchingImages":
                    match_image_url = items[0].get("url")
                else:
                    full = (items[0].get("fullMatchingImages") or [])
                    if full:
                        match_image_url = full[0].get("url")
                if match_image_url:
                    break

        match_page_url = None
        pages = web.get("pagesWithMatchingImages") or []
        if pages:
            match_page_url = pages[0].get("url")

        if not best_guess and not match_image_url and not match_page_url:
            return None
        return {
            "best_guess": best_guess,
            "match_image_url": match_image_url,
            "match_page_url": match_page_url,
        }
    except Exception as e:
        print(f"  [WARN] Google Vision web detection failed: {e}")
        return None


def wikipedia_article_info(title):
    """Return (summary_text, original_image_url) for a Wikipedia article title."""
    try:
        resp = requests.get(
            WIKI_API,
            params={
                "action": "query",
                "prop": "extracts|pageimages",
                "exintro": 1,
                "explaintext": 1,
                "piprop": "original",
                "titles": title,
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for _, page in pages.items():
            extract = page.get("extract", "")
            image_url = page.get("original", {}).get("source")
            return extract, image_url
    except Exception as e:
        print(f"  [WARN] Wikipedia article lookup failed for {title!r}: {e}")
    return "", None


def download_image(url, out_path):
    for attempt in range(1, DOWNLOAD_MAX_RETRIES + 1):
        try:
            time.sleep(DOWNLOAD_SLEEP_SEC * attempt)
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
                stream=True,
            )
            if resp.status_code == 429:
                print(f"  [WARN] 429 rate-limited, retry {attempt}/{DOWNLOAD_MAX_RETRIES}...")
                continue
            resp.raise_for_status()
            content = resp.content
            if len(content) < MIN_FULLRES_BYTES:
                return False
            with open(out_path, "wb") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"  [WARN] download failed for {url}: {e}")
            return False
    return False


def search_and_enrich(caption_text, image_bytes, index, enriched_dir, vision_api_key):
    """Identify the photo and return (info_text, downloaded_image_path or None).

    Tries true reverse image search (Google Vision Web Detection) first, using
    the actual frame pixels. Falls back to an OCR-caption text search against
    Wikipedia (relevance-filtered) if Vision isn't configured or finds nothing.
    """
    vision_result = google_vision_web_detection(image_bytes, vision_api_key)
    if vision_result:
        label = vision_result.get("best_guess")
        match_image_url = vision_result.get("match_image_url")
        match_page_url = vision_result.get("match_page_url")
        print(f"  [VISION] best guess: {label!r} page: {match_page_url}")

        downloaded_path = None
        if match_image_url:
            ext = os.path.splitext(match_image_url.split("?")[0])[1] or ".jpg"
            ext = ext if len(ext) <= 5 else ".jpg"
            candidate_path = os.path.join(enriched_dir, f"fullres--{index}{ext}")
            if download_image(match_image_url, candidate_path):
                downloaded_path = candidate_path

        info_text = None
        if match_page_url:
            info_text = clean_info_text(fetch_page_description(match_page_url))
        if not info_text and label:
            # Fall back to a Wikipedia summary of the Vision label, which tends
            # to be a much cleaner search term than the raw OCR caption.
            titles = wikipedia_search(label)
            time.sleep(SEARCH_SLEEP_SEC)
            for title in titles:
                extract, wiki_image_url = wikipedia_article_info(title)
                if extract:
                    info_text = clean_info_text(extract)
                if not downloaded_path and wiki_image_url:
                    ext = os.path.splitext(wiki_image_url.split("?")[0])[1] or ".jpg"
                    ext = ext if len(ext) <= 5 else ".jpg"
                    candidate_path = os.path.join(enriched_dir, f"fullres--{index}{ext}")
                    if download_image(wiki_image_url, candidate_path):
                        downloaded_path = candidate_path
                if info_text:
                    break

        if info_text or downloaded_path:
            print(f"  [MATCH] via reverse image search")
            return (info_text or label), downloaded_path
        print("  [VISION] no usable description/image from web detection result")

    # Fallback: OCR-caption text search against Wikipedia.
    query = clean_search_query(caption_text)
    if not query:
        return None, None

    print(f"  [SEARCH] Wikipedia text-query fallback: {query!r}")
    titles = wikipedia_search(query)
    time.sleep(SEARCH_SLEEP_SEC)

    if not titles:
        print("  [SEARCH] no relevant Wikipedia matches")
        return None, None

    for title in titles:
        extract, image_url = wikipedia_article_info(title)
        if not extract and not image_url:
            continue

        info_text = clean_info_text(extract) if extract else None
        downloaded_path = None
        if image_url:
            ext = os.path.splitext(image_url.split("?")[0])[1] or ".jpg"
            ext = ext if len(ext) <= 5 else ".jpg"
            candidate_path = os.path.join(enriched_dir, f"fullres--{index}{ext}")
            if download_image(image_url, candidate_path):
                downloaded_path = candidate_path

        if info_text or downloaded_path:
            print(f"  [MATCH] Wikipedia article: {title!r}")
            return info_text, downloaded_path

    return None, None


def process_one(video, anchor_sec, index, enriched_dir, text_offset_sec, text_search_window_sec, vision_api_key):
    frame = base.find_best_frame_for_step(video, anchor_sec)
    if frame is None:
        return False

    caption_anchor = max(0.0, frame["sec"] - text_offset_sec)
    caption_text, _ = base.extract_best_caption_text(
        video, caption_anchor, search_window_sec=text_search_window_sec
    )
    if not caption_text:
        caption_text = "image"

    print(f"[#{index}] frame={frame['sec']:.1f}s ocr_caption={caption_text[:90]!r}")

    ok, encoded_frame = cv2.imencode(".jpg", frame["photo"])
    frame_bytes = encoded_frame.tobytes() if ok else b""

    info_text, fullres_path = search_and_enrich(
        caption_text, frame_bytes, index, enriched_dir, vision_api_key
    )

    summary = base.summarize_text(caption_text, base.MAX_SUMMARY_WORDS)
    filename = f"{summary}--{index}.png"
    photo_path = os.path.join(OUTPUT_DIR, filename)

    if fullres_path:
        print(f"  [OK] downloaded full-res image -> {fullres_path}")
        final_image_path = fullres_path
    else:
        cv2.imwrite(photo_path, frame["photo"])
        final_image_path = photo_path
        print(f"  [FALLBACK] kept cropped video frame -> {photo_path}")

    final_text = info_text or caption_text
    text_path = os.path.join(OUTPUT_DIR, TEXT_FILE)
    with open(text_path, "a", encoding="utf-8") as f:
        f.write(f"{index} | {final_text}\n")

    print(f"  [TEXT] {index} | {final_text}")
    print(f"  [IMAGE] {final_image_path}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Extract photos from a video, identify them via reverse image search "
                    "(Google Vision) or a Wikipedia text-search fallback, download "
                    "full-resolution versions when available, and write descriptions."
    )
    parser.add_argument("video", help="Path to the source video")
    parser.add_argument("--start-sec", type=float, default=base.START_SEC)
    parser.add_argument("--step-sec", type=float, default=base.STEP_SEC)
    parser.add_argument("--text-offset-sec", type=float, default=base.TEXT_OFFSET_SEC)
    parser.add_argument("--text-search-window", type=float, default=base.TEXT_SEARCH_WINDOW_SEC)
    parser.add_argument("--max-frames", type=int, default=3, help="Number of photos to process (default: 3 for testing)")
    args = parser.parse_args()

    video = args.video
    if not os.path.isfile(video):
        print(f"Error: file not found: {video}")
        sys.exit(1)

    vision_api_key = resolve_vision_api_key()
    if vision_api_key:
        print("[INFO] GOOGLE_VISION_API_KEY found -- using reverse image search.")
    else:
        print(
            "[INFO] No GOOGLE_VISION_API_KEY configured -- falling back to a "
            "stricter OCR-caption Wikipedia text search (lower hit rate). "
            "Add GOOGLE_VISION_API_KEY to .env to enable true reverse image search."
        )

    video_input, temp_video_alias = base.prepare_ffmpeg_video_input(video)
    if temp_video_alias is not None:
        print(f"[INFO] Using ffmpeg-safe alias: {os.path.basename(video_input)}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    enriched_dir = os.path.join(OUTPUT_DIR, ENRICHED_SUBDIR)
    os.makedirs(enriched_dir, exist_ok=True)

    text_path = os.path.join(OUTPUT_DIR, TEXT_FILE)
    index = base.get_next_index(text_path)

    try:
        duration = base.get_video_duration(video_input)
    except Exception as e:
        print(f"Error getting duration: {e}")
        sys.exit(1)

    print(f"Video duration: {duration:.2f}s")
    print(f"Test mode: processing up to {args.max_frames} photo(s)")

    anchor = args.start_sec
    processed = 0
    while anchor < duration - 1 and processed < args.max_frames:
        ok = process_one(
            video_input,
            anchor,
            index,
            enriched_dir,
            text_offset_sec=max(0.0, float(args.text_offset_sec)),
            text_search_window_sec=max(0.5, float(args.text_search_window)),
            vision_api_key=vision_api_key,
        )
        if ok:
            index += 1
            processed += 1
        anchor += args.step_sec

    if os.path.exists(TEMP_FRAME):
        try:
            os.remove(TEMP_FRAME)
        except OSError:
            pass
    if temp_video_alias is not None and os.path.exists(temp_video_alias):
        try:
            os.remove(temp_video_alias)
        except OSError:
            pass

    print(f"[DONE] processed {processed} photo(s)")


if __name__ == "__main__":
    main()
