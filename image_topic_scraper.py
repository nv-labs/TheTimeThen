#!/usr/bin/env python3
"""
image_topic_scraper.py

Search the web for images on a given topic and save them into a folder,
together with a text file describing each image.

Each image filename ends with a number (e.g. miami_1970s_photos--3.jpg)
and that same number is the line number/prefix in the info text file
(e.g. "3 | <description>"), so every image and its text entry stay
linked by that number -- matching the format of the reference text file
that was provided (lines like "63 | a telephone from the 1950s.").

Usage:
    python image_topic_scraper.py "Miami 1970s photos" --count 5

    # custom output folder name
    python image_topic_scraper.py "Miami 1970s photos" --count 10 --outdir my_folder

Results from watermarked stock-photo agencies (Alamy, Getty Images,
Shutterstock, iStock, Dreamstime, 123RF, etc.) are automatically skipped,
since those sites only serve watermarked preview images without a paid
license -- there's no clean version to download from them.

Descriptions for each photo are generated locally using Ollama (a free,
open-source local LLM runner) with the deepseek-r1:7b model -- no OpenAI
account or API key required. Ollama must be installed and running
(https://ollama.com) with that model pulled:
    ollama pull deepseek-r1:7b
If Ollama isn't reachable, the script automatically falls back to a
heuristic (non-AI) description picker, and OpenAI is used only as a last
resort if OPENAI_API_KEY is configured in .env.

Requires:
    pip install ddgs requests pillow beautifulsoup4 openai ftfy
"""

import argparse
import hashlib
import io
import os
import re
import time
from collections import Counter
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from ddgs import DDGS  # current package name
except ImportError:
    from duckduckgo_search import DDGS  # older package name, fallback

try:
    from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, APIError
except ImportError:
    OpenAI = None
    APITimeoutError = APIConnectionError = RateLimitError = APIError = Exception

# ================= LOCAL LLM (Ollama) CONFIG =================
# Ollama exposes an OpenAI-compatible API locally -- no API key or internet
# connection needed. Point the OpenAI client at it and use a local model name
# instead of a real OpenAI model.
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "deepseek-r1:7b"
OLLAMA_API_KEY = "ollama"  # unused by Ollama but required by the client

try:
    import ftfy  # repairs mis-decoded ("mojibake") text, e.g. "BÃ¶hm" -> "Böhm"
except ImportError:
    ftfy = None


def _fix_text_encoding(text: str) -> str:
    if not text or ftfy is None:
        return text
    return ftfy.fix_text(text)


# Stock/agency sites that only serve watermarked preview images unless paid
# for. There's no clean version of these to hotlink, so we skip the whole
# domain rather than download and end up with a watermark in the output.
WATERMARKED_STOCK_DOMAINS = {
    "alamy.com",
    "gettyimages.com",
    "gettyimages.co.uk",
    "istockphoto.com",
    "shutterstock.com",
    "dreamstime.com",
    "123rf.com",
    "depositphotos.com",
    "stock.adobe.com",
    "bigstockphoto.com",
    "canstockphoto.com",
    "agefotostock.com",
    "vectorstock.com",
    "pond5.com",
    "stockphoto.com",
    "fotolia.com",
}


def is_watermarked_stock_source(*urls: str) -> bool:
    """True if any of the given URLs point at a known watermarked stock-photo agency."""
    for url in urls:
        if not url:
            continue
        host = urlparse(url).netloc.lower()
        for domain in WATERMARKED_STOCK_DOMAINS:
            if host == domain or host.endswith("." + domain):
                return True
    return False


# Social/video platform pages (channel pages, posts, etc.) never contain real
# article text -- fetching them typically returns a cookie-consent wall,
# login prompt, or just the channel/account name, none of which describe the
# photo. Skip fetching page content for these entirely.
SOCIAL_PLATFORM_DOMAINS = {
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
    "facebook.com", "twitter.com", "x.com", "reddit.com",
}


def _is_social_platform_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in SOCIAL_PLATFORM_DOMAINS)


# Wallpaper/background-download sites host real photos but their page text
# (title, meta description, body) describes the *website's wallpaper
# collection* ("98 free wallpapers for desktop, phone, tablet"), not the
# photo's actual subject/history -- using that text as a caption is
# technically-true-but-useless noise, not a description of the photo.
WALLPAPER_HOST_DOMAINS = {
    "wallpaperaccess.com", "wallpapercave.com", "wallpapers.com",
    "wallpaperflare.com", "hdqwalls.com", "pngtree.com", "vecteezy.com",
    "wallpapersafari.com", "wallpaperbetter.com", "getwallpapers.com",
}

# Link-aggregator / "suggestions" sites that mirror images alongside
# completely unrelated content pulled from other topics -- their page title
# can describe a totally different subject than the actual photo (e.g. an
# American-flag article title attached to a New York City street photo).
LINK_AGGREGATOR_DOMAINS = {
    "fity.club",
}


def _is_wallpaper_host_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in WALLPAPER_HOST_DOMAINS)


def _is_link_aggregator_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in LINK_AGGREGATOR_DOMAINS)


# ================= TOPIC RELEVANCE CHECK =================
# Scraped titles/text are sometimes completely unrelated to the actual photo
# (mirror/aggregator sites that list unrelated "suggested" content). Before
# trusting any scraped text as caption material, check that it actually
# shares real keywords with the search topic -- text with zero overlap is
# untrustworthy and should never be used, generic filler words in the topic
# itself (like "old", "photos", "vintage") don't count as meaningful overlap.

TOPIC_FILLER_WORDS = {
    "old", "photo", "photos", "photograph", "photographs", "picture",
    "pictures", "image", "images", "vintage", "rare", "historical",
    "history", "antique", "classic", "of", "the", "in", "and", "for",
    "a", "an", "from",
}


def _topic_keywords(topic: str):
    words = re.findall(r"[A-Za-z0-9]+", (topic or "").lower())
    return {w for w in words if w not in TOPIC_FILLER_WORDS and len(w) >= 3}


def _text_matches_topic(text: str, topic_keywords: set) -> bool:
    """True if text shares at least one meaningful keyword with the topic,
    or if the topic had no meaningful keywords to check against (nothing to
    compare, so we can't rule it out).
    """
    if not topic_keywords:
        return True
    if not text:
        return False
    text_words = set(re.findall(r"[A-Za-z0-9]+", text.lower()))
    return bool(topic_keywords & text_words)


def slugify(text: str) -> str:
    """Turn 'Miami 1970s photos' into 'miami_1970s_photos'."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def guess_extension(url: str, content_type: str) -> str:
    """Pick a sensible file extension from the URL or the response headers."""
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext == ".jpeg":
        return ".jpg"
    if ext in (".jpg", ".png", ".webp", ".gif", ".bmp"):
        return ext
    if content_type:
        if "png" in content_type:
            return ".png"
        if "webp" in content_type:
            return ".webp"
        if "gif" in content_type:
            return ".gif"
    return ".jpg"


# ================= DUPLICATE / NEAR-DUPLICATE IMAGE DETECTION =================
# Two layers, same approach used elsewhere in this project
# (auto_extract_historical_photos.py): an exact byte-hash for identical
# files, plus a perceptual hash (dHash) + Hamming distance for near-duplicates
# (same photo re-encoded/resized/cropped/watermarked slightly differently
# across different source sites).

DHASH_SIZE = 8
NEAR_DUPLICATE_DISTANCE_THRESHOLD = 6  # out of 64 bits; lower = stricter


def compute_exact_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def compute_dhash(image_bytes: bytes, hash_size: int = DHASH_SIZE):
    """Perceptual difference-hash: robust to re-encoding/resizing/minor crops,
    unlike an exact byte hash. Returns a hex string, or None if the bytes
    aren't a readable image (e.g. Pillow isn't installed, or corrupt data).
    """
    if Image is None:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
            pixels = img.tobytes()  # single-channel ("L" mode) -> 1 byte/pixel
    except Exception:
        return None

    bits = []
    width = hash_size + 1
    for row in range(hash_size):
        row_start = row * width
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            bits.append("1" if left > right else "0")
    return format(int("".join(bits), 2), "016x")


def hamming_distance(hash_a: str, hash_b: str) -> int:
    if not hash_a or not hash_b or len(hash_a) != len(hash_b):
        return 999
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def find_duplicate(image_bytes: bytes, seen_images: list):
    """Check image_bytes against every previously-saved image this run.
    Returns a short reason string ("exact" / "near-duplicate (d=N)") if a
    match is found, else None.
    """
    exact_hash = compute_exact_hash(image_bytes)
    dhash = compute_dhash(image_bytes)

    for entry in seen_images:
        if exact_hash == entry["exact_hash"]:
            return "exact duplicate"
        if dhash and entry["dhash"]:
            distance = hamming_distance(dhash, entry["dhash"])
            if distance <= NEAR_DUPLICATE_DISTANCE_THRESHOLD:
                return f"near-duplicate (d={distance})"
    return None


TRAILING_ELLIPSIS_RE = re.compile(r"\s*(\.\.\.|…)\s*$")


def _is_truncated(text: str) -> bool:
    return bool(TRAILING_ELLIPSIS_RE.search(text or ""))


def _strip_trailing_ellipsis(text: str) -> str:
    return TRAILING_ELLIPSIS_RE.sub("", text or "").strip()


def _trim_to_last_complete_sentence(text: str) -> str:
    """If text has sentence-ending punctuation, cut at the last one so we
    never leave a dangling half-sentence. Otherwise return text unchanged
    (a trailing period will be added by the caller if needed).
    """
    matches = list(re.finditer(r"[.!?](?:\s|$)", text))
    if matches:
        end = matches[-1].end()
        return text[:end].strip()
    return text.strip()


QUOTE_CHARS = "\"'\u2018\u2019\u201c\u201d"


def _strip_unbalanced_quote(text: str) -> str:
    """Drop a leading quote mark that has no matching closing quote (common
    when a blockquote fragment is pulled out of its surrounding context).
    """
    if not text:
        return text
    if text[0] in QUOTE_CHARS and sum(1 for ch in text if ch in QUOTE_CHARS) % 2 == 1:
        text = text[1:].lstrip()
    return text


# ================= JUNK / CREDIT-LINE FILTERING =================
# Scraped titles/snippets are frequently just a publication name, a section
# label ("Opinion."), or a photo credit line -- none of which describe the
# photo itself. These are filtered out before being used as (or fed into)
# the description text.

PUBLICATION_NAMES = {
    "bbc news", "bbc", "the new york times", "new york times", "the times",
    "the guardian", "the washington post", "washington post", "cnn",
    "associated press", "reuters", "afp", "getty images", "the atlantic",
    "npr", "the telegraph", "usa today", "the independent", "time magazine",
    "life magazine", "national geographic", "smithsonian magazine",
    "history.com", "wikipedia", "flickr", "pinterest", "artofit",
    "flickriver", "vintage everyday", "vintag es", "the sun", "daily mail",
    "abc news", "cbs news", "nbc news", "fox news", "huffpost", "vox",
    "youtube", "instagram", "tiktok", "facebook", "twitter", "reddit",
}

# Video/social platform titles are almost always just a channel/account name
# or handle (e.g. "Youtube - @Celebrity Lifestyle & Moments"), never an
# actual description of the photo -- filter these out entirely.
PLATFORM_CHANNEL_RE = re.compile(
    r"""(
        \byoutube\b
        | ^\s*[\w.\s]{1,40}-\s*@\w   # "<Site/Channel Name> - @handle"
        | ^\s*@\w[\w.]*\s*(-|\|)     # "@handle - ..." / "@handle | ..."
    )""",
    re.IGNORECASE | re.VERBOSE,
)

SECTION_LABELS = {
    "opinion", "news", "photos", "photo", "gallery", "world", "world news",
    "us news", "video", "live", "breaking news", "analysis", "feature",
    "features", "editorial", "home", "front page",
}

CREDIT_LINE_RE = re.compile(
    r"""(
        ^\s*(photo|photograph|image|credit)s?\s*(:|by)\b.*$   # "Photo by ..." / "Credit: ..."
        | \(\s*(getty|ap|afp|reuters|epa|alamy|shutterstock)[^)]*\)  # "(Getty Images)" etc.
        | \b(getty\s+images|associated\s+press|afp|reuters|epa\s+photo)\b
        | ^\s*(via|source)\s*:.*$
        | ^\s*(now\s+reading|read\s+more|related|you\s+may\s+also\s+like|share\s+this|advertisement)\s*:?.*$
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# Site boilerplate (newsletter signup, cookie/privacy notices, copyright
# footers) that sometimes ends up in the first few <p> tags of a page but
# never describes the photo itself.
BOILERPLATE_RE = re.compile(
    r"""(
        \bsign(ing)?\s+up\b
        | \bnewsletter\b
        | \bsubscribe\b
        | \bprivacy\s+polic(y|ies)\b
        | \bprivacy\s+notice\b
        | \bterms\s+of\s+(service|use)\b
        | \bcookie(s)?\b
        | \ball\s+rights\s+reserved\b
        | \bcopyright\s*(\N{COPYRIGHT SIGN}|\(c\))?\s*\d{0,4}\b
        | \bi\s+would\s+like\s+to\s+be\s+emailed\b
        | \b(offers|events?)\s+and\s+updates\s+from\b
        | \bif\s+you\s+liked\s+this\s+post\b
        | \bcheck\s+out\s+these\s+(popular\s+)?posts\b
        | \brelated\s+posts\b
        | \bfree\s+wallpapers?\b
        | \bwallpapers?\s+(and|or)\s+backgrounds?\b
        | \bfor\s+(your\s+)?(desktop|phone|tablet|mobile|smartphone)s?\b
        | \bhd\s+(wallpaper|images?)s?\b
        | \bhome\s+screen\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# Site self-promotion taglines ("Your Ultimate Source for ... at Site.com!")
# and clickbait/poll/meme-vote lines -- neither describes the photo.
SITE_PROMO_RE = re.compile(
    r"""(
        \byour\s+(ultimate\s+)?(source|destination|home)\s+for\b
        | \b[\w-]+\.(com|org|net|film|co|io)\b   # embedded site domain mention
        | \bwho\s+won\b
        | \bmeme\s+of\s+the\s+(month|week|day|year)\b
        | \bvote\s+for\b
        | \bpoll\s+for\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)

MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
)
# Blog/CMS post metadata lines, e.g. "March 2, 2018 Vintage Everyday 1980s ,
# life & culture , New York , people , street 0."
POST_DATE_PREFIX_RE = re.compile(
    r"^\s*(" + "|".join(MONTH_NAMES) + r")\s+\d{1,2},?\s+\d{4}\b", re.IGNORECASE
)


def _looks_like_tag_list(text: str) -> bool:
    """True if text reads like a comma-separated list of category/tag labels
    (post metadata) rather than an actual sentence -- e.g.
    'life & culture , New York , people , street 0'.
    """
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) < 3:
        return False
    short = sum(1 for p in parts if len(p.split()) <= 3)
    has_sentence_punct = bool(re.search(r"[.!?]\s+[A-Z]", text))
    return (short / len(parts)) >= 0.7 and not has_sentence_punct


def _is_junk_line(text: str) -> bool:
    """True if text is nothing but a publication name, section label, byline,
    photo-credit line, or blog-post metadata (date/tag list) -- i.e. not an
    actual description of the photo.
    """
    if not text:
        return True
    stripped = text.strip().strip(".!?").strip()
    key = stripped.lower()
    if not key:
        return True
    if key in PUBLICATION_NAMES or key in SECTION_LABELS:
        return True
    if PLATFORM_CHANNEL_RE.search(text):
        return True
    if POST_DATE_PREFIX_RE.match(stripped) or _looks_like_tag_list(stripped):
        return True
    if CREDIT_LINE_RE.search(text):
        # Only treat as junk if the credit line makes up most of the text
        # (a short factual sentence that happens to mention "AP" elsewhere
        # should not be discarded).
        residual = CREDIT_LINE_RE.sub("", text).strip()
        if len(residual) < 8:
            return True
    if BOILERPLATE_RE.search(text):
        return True
    if SITE_PROMO_RE.search(text):
        return True
    # Bare byline pattern, e.g. "By John Smith" / "By Jane Doe, BBC News"
    if re.match(r"^\s*by\s+[A-Z][a-zA-Z.'-]+(\s+[A-Z][a-zA-Z.'-]+){0,3}\s*$", stripped):
        return True
    return False


def _strip_credit_lines(text: str) -> str:
    """Remove embedded credit-line fragments from an otherwise-useful string,
    without discarding the whole thing.
    """
    text = CREDIT_LINE_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip(" -|,")


def _image_url_basename(url: str) -> str:
    """Extract a comparable filename/basename from an image URL, stripping
    query strings and common CDN resize suffixes so it can be matched
    against <img src="..."> attributes found in the page HTML.
    """
    if not url:
        return ""
    path = urlparse(url).path
    name = os.path.basename(path).lower()
    return name


def _extract_image_specific_caption(soup: BeautifulSoup, image_url: str):
    """Best-effort: find the <img> tag on the page whose src/srcset matches
    image_url, then read its nearby caption (figcaption, alt text, or an
    adjacent <em>/<p> -- the common WordPress/blog "photo caption" pattern).

    This matters because many source pages are multi-photo galleries/
    listicles ("36 vintage photos of X") where a single page hosts dozens of
    different photos, each with its own specific caption. Falling back to
    the page's overall title/meta description/body text in that case risks
    describing a completely different photo than the one actually
    downloaded. Returns None if no confident match is found.
    """
    target = _image_url_basename(image_url)
    if not target:
        return None

    for img in soup.find_all("img"):
        candidates = [img.get("src", ""), img.get("data-src", ""), img.get("srcset", "")]
        if not any(target in c.lower() for c in candidates if c):
            continue

        # 1) <figure><img>...<figcaption>caption</figcaption></figure>
        figure = img.find_parent("figure")
        if figure:
            figcaption = figure.find("figcaption")
            if figcaption:
                text = _fix_text_encoding(unescape(figcaption.get_text(" ", strip=True)))
                if len(text) >= 15 and not _is_junk_line(text):
                    return text

        # 2) Non-empty, descriptive alt text (skip generic/empty alts)
        alt = _fix_text_encoding(unescape((img.get("alt") or "").strip()))
        if len(alt) >= 15 and not _is_junk_line(alt):
            return alt

        # 3) A caption-styled tag immediately following the image (common in
        # WordPress posts: <img>...<p><em>Caption text.</em></p>)
        sibling = img.find_next(["em", "i", "small", "p"])
        if sibling:
            text = _fix_text_encoding(unescape(sibling.get_text(" ", strip=True)))
            if 15 <= len(text) <= 300 and not _is_junk_line(text):
                return text

        return None  # matched the image but found no usable caption nearby

    return None


def fetch_page_content(source_url: str, image_url: str = None):
    """Fetch a page once and return a dict of useful text signals:
      title, meta_description, paragraphs (list of body paragraph strings),
      image_caption (a caption tied specifically to image_url, if found --
      see _extract_image_specific_caption)
    Returns None if the page could not be fetched.
    """
    if not source_url:
        return None
    try:
        resp = requests.get(
            source_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ImageTopicScraper/1.0)"},
            timeout=10,
        )
        resp.raise_for_status()
        # Parse from raw bytes (not resp.text) so BeautifulSoup can detect the
        # page's real encoding from its <meta charset> tag -- using resp.text
        # lets requests guess the encoding, which is frequently wrong and
        # produces mojibake (e.g. "Ã¶" instead of "ö").
        soup = BeautifulSoup(resp.content, "html.parser")

        title = ""
        for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                title = _fix_text_encoding(unescape(tag["content"].strip()))
                break
        if not title and soup.title and soup.title.string:
            title = _fix_text_encoding(unescape(soup.title.string.strip()))

        meta_description = ""
        for attrs in ({"property": "og:description"}, {"name": "description"}, {"name": "twitter:description"}):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                meta_description = _fix_text_encoding(unescape(tag["content"].strip()))
                break

        paragraphs = []
        for p in soup.find_all("p"):
            text = _fix_text_encoding(unescape(p.get_text(" ", strip=True)))
            if len(text) >= 40 and not _is_junk_line(text):
                paragraphs.append(text)
            if len(paragraphs) >= 6:
                break

        image_caption = _extract_image_specific_caption(soup, image_url) if image_url else None

        return {
            "title": title,
            "meta_description": meta_description,
            "paragraphs": paragraphs,
            "image_caption": image_caption,
        }
    except Exception as e:
        print(f"  [WARN] could not fetch page content from {source_url}: {e}")
        return None


# ================= LLM CLIENT (local Ollama first, OpenAI fallback) =================

_llm_client = None       # (client, model_name) tuple once resolved
_llm_unavailable = False


def _read_dotenv_key(dotenv_path, key_name):
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


def _resolve_openai_key():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return _read_dotenv_key(os.path.join(script_dir, ".env"), "OPENAI_API_KEY")


def _try_ollama_client():
    """Return (client, model) if a local Ollama server is reachable and has
    OLLAMA_MODEL available, else None. Ollama requires no API key/internet.
    """
    if OpenAI is None:
        return None
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/models", timeout=3)
        resp.raise_for_status()
        available = {m.get("id") for m in resp.json().get("data", [])}
    except Exception:
        return None

    if OLLAMA_MODEL not in available:
        print(f"  [WARN] Ollama is running but model '{OLLAMA_MODEL}' is not pulled "
              f"(run: ollama pull {OLLAMA_MODEL}); available: {sorted(available)}")
        return None

    try:
        client = OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
        return (client, OLLAMA_MODEL)
    except Exception:
        return None


def _try_openai_client():
    if OpenAI is None:
        return None
    api_key = _resolve_openai_key()
    if not api_key or api_key.strip().lower() in ("", "sk-your-key-here") or "your-key-here" in api_key.lower():
        return None
    try:
        client = OpenAI(api_key=api_key)
        return (client, "gpt-4o-mini")
    except Exception:
        return None


def _get_llm_client():
    """Resolve once: prefer the local Ollama server (free, no API key,
    fully open-source) and only fall back to real OpenAI if Ollama isn't
    reachable/configured. Returns (client, model_name) or None.
    """
    global _llm_client, _llm_unavailable
    if _llm_unavailable:
        return None
    if _llm_client is not None:
        return _llm_client

    resolved = _try_ollama_client()
    if resolved:
        print(f"  [INFO] Using local Ollama model '{resolved[1]}' for descriptions.")
    else:
        resolved = _try_openai_client()
        if resolved:
            print(f"  [INFO] Ollama unavailable -- falling back to OpenAI model '{resolved[1]}'.")

    if not resolved:
        _llm_unavailable = True
        return None

    _llm_client = resolved
    return _llm_client


THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _strip_reasoning_block(text: str) -> str:
    """Reasoning models (like deepseek-r1) sometimes emit their chain-of-
    thought wrapped in <think>...</think> before the actual answer -- strip
    it so only the final caption text remains.
    """
    return THINK_BLOCK_RE.sub("", text).strip()


YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20[0-4]\d)\b")


def _extract_years(text: str) -> set:
    return set(YEAR_RE.findall(text or ""))


def _is_grounded(generated_text: str, context_text: str) -> bool:
    """Reject captions where the LLM invents a specific year that appears
    nowhere in the scraped context -- a strong, easy-to-check signal of
    hallucination (fabricating a vivid-sounding but made-up date/event) when
    the source page had little or no real information about the photo.
    """
    generated_years = _extract_years(generated_text)
    if not generated_years:
        return True
    context_years = _extract_years(context_text)
    return generated_years.issubset(context_years)


def _context_is_substantive(page: dict, image_caption) -> bool:
    """True if there is real, substantive scraped text to ground a caption in
    (a matched per-image caption, real body paragraphs, or a meaningful meta
    description) -- as opposed to just a bare page title. Thin/near-empty
    context is exactly when a local LLM is most likely to fabricate a
    plausible-sounding but entirely made-up "fact" instead of admitting it
    has nothing to say.
    """
    if image_caption:
        return True
    if not page:
        return False
    if page.get("paragraphs"):
        return True
    meta = page.get("meta_description") or ""
    return len(meta) >= 40


def generate_interesting_description(topic: str, title: str, page: dict, is_gallery_page: bool = False):
    """Ask a local LLM (Ollama, preferred) or OpenAI (fallback) for one or
    two interesting, factual sentences about the photo itself, using the
    scraped title/description/body text as context. Returns None if no LLM
    is available, there isn't enough real context to ground a factual
    caption in, the generated caption looks hallucinated (invents a year not
    present anywhere in the source text), or the call fails -- in all of
    those cases the caller falls back to the heuristic (non-generative) path.

    is_gallery_page: True when the source page is known to host multiple
    different photos (a listicle/gallery, e.g. "45 vintage photos of X").
    In that case the page's generic body text/meta description may describe
    a *different* photo than the one actually downloaded, so it is excluded
    from context unless we found a caption tied specifically to this image
    (page['image_caption']).
    """
    resolved = _get_llm_client()
    if resolved is None:
        return None
    client, model = resolved

    image_caption = page.get("image_caption") if page else None

    # Guard against hallucination: if there's no real, specific text to
    # ground a caption in, don't ask the LLM to invent one -- a nearly-empty
    # source page (e.g. a generic wallpaper listing) is exactly the scenario
    # where a local model is prone to fabricating a vivid but fake "fact".
    if not _context_is_substantive(page, image_caption):
        return None

    if image_caption:
        # We matched this exact <img> tag on the page and found its own
        # caption/alt text -- this is trustworthy, photo-specific context.
        context = f'Caption specifically written for this exact photo: "{image_caption}"\nPage title: {title}'
        specificity_note = (
            "The caption above describes this exact photo and is reliable. "
            "You may lightly rephrase it into a natural sentence, but do not add "
            "invented details beyond what it says."
        )
    elif is_gallery_page:
        # No per-image caption could be matched, and this page hosts many
        # different photos -- its body text is NOT reliably about this
        # specific image, so it is deliberately withheld from context.
        context = f"Page title (this photo is one of several from a larger photo collection): {title}"
        specificity_note = (
            "You do NOT have any text that specifically describes this exact photo "
            "(only the title of the larger collection it came from). Do NOT invent "
            "specific visual details, actions, people, or events that you cannot "
            "confirm. If you cannot say anything both specific and true, respond "
            "with exactly: NONE"
        )
    else:
        context_bits = [title]
        if page:
            if page.get("meta_description"):
                context_bits.append(page["meta_description"])
            context_bits.extend(page.get("paragraphs", [])[:3])
        context = "\n".join(b for b in context_bits if b)[:2500]
        specificity_note = ""

    prompt = f"""You are writing a short caption for a historical/interest photo used in a video slideshow.

Topic the photo was found under: "{topic}"

Here is text scraped from the web page where this photo appeared (may include
noise like site navigation, ads, or unrelated content -- ignore anything not
actually about the photo):

{context}

{specificity_note}

Write ONE or maximum TWO sentences describing something genuinely interesting
or informative about this specific photo (who/what/where/when, or an
interesting fact about it). 

Rules (very important):
- ONLY use facts, years, dates, names, and events that literally appear in the
  text above. Do NOT invent or guess a year, date, named ship/building/person,
  or event that is not explicitly given -- fabricating a plausible-sounding
  detail is strictly forbidden, even if the text is thin.
- Do NOT mention the publication, website, news outlet, or photographer credit
  (no "BBC News", "Associated Press", "Getty Images", "The New York Times", etc.)
- Do NOT output section labels like "Opinion" or "News"
- Do NOT say things like "This image shows..." or "This photo depicts..." -- just state the fact directly
- If the scraped text has no real information about the photo, respond with exactly: NONE
- Output ONLY the caption sentence(s), nothing else
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            timeout=60,
        )
        result = (response.choices[0].message.content or "").strip()
    except (APITimeoutError, APIConnectionError, RateLimitError, APIError) as e:
        print(f"  [WARN] LLM description generation failed: {e}")
        return None
    except Exception as e:
        print(f"  [WARN] LLM description generation failed: {e}")
        return None

    result = _strip_reasoning_block(result)
    result = re.sub(r"\s+", " ", result).strip()
    if not result or result.upper() == "NONE" or _is_junk_line(result):
        return None

    if not _is_grounded(result, context):
        print(f"  [WARN] discarding likely-hallucinated caption (invented a year not in source text): {result[:100]}")
        return None

    return result


def _first_title_segment(title: str) -> str:
    """Titles are often 'Main Title | Site Name' or 'Main Title - Site Name'
    (using a pipe or an en/em dash as separator) -- keep only the first part.
    """
    if not title:
        return title
    match = re.split(r"\s[\|\u2013\u2014]\s", title, maxsplit=1)
    return match[0].strip()


def _heuristic_description(title: str, page: dict, is_gallery_page: bool = False) -> str:
    """Fallback path (no LLM available, or the LLM declined): pick the best
    1-2 non-junk sentences of context, otherwise fall back to the cleaned
    title.

    Priority order:
      1. page['image_caption'] -- text tied specifically to this exact photo
         (found by matching its <img> tag on the page), always safe to use.
      2. page['paragraphs'] / page['meta_description'] -- generic page-level
         text. Only used when is_gallery_page is False, since on a gallery/
         listicle page (many different photos, one shared page) this text
         may describe a different photo entirely.
      3. The page/article title -- never claims specific visual details, so
         always safe even on a gallery page.
    """
    title = _first_title_segment((title or "").strip())

    candidates = []
    if page:
        if page.get("image_caption"):
            candidates.append(page["image_caption"])
        if not is_gallery_page:
            candidates.extend(page.get("paragraphs", []))
            if page.get("meta_description"):
                candidates.append(page["meta_description"])

    for candidate in candidates:
        was_truncated = _is_truncated(candidate)
        candidate = _strip_credit_lines(candidate)
        if was_truncated:
            candidate = _strip_trailing_ellipsis(candidate)

        raw_sentences = re.split(r"(?<=[.!?])\s+", candidate)
        if raw_sentences and was_truncated and not re.search(r"[.!?]$", raw_sentences[-1].strip()):
            # The site cut this text off mid-word/mid-sentence (no way to
            # recover what came after) -- drop the broken trailing fragment
            # rather than writing a dangling half-sentence.
            raw_sentences = raw_sentences[:-1]

        sentences = [s.strip() for s in raw_sentences if s.strip() and not _is_junk_line(s)]
        if not sentences:
            continue
        chosen = " ".join(sentences[:2]).strip()
        if len(chosen) >= 20:
            return chosen

    # Nothing usable in the page content -- fall back to the title itself,
    # unless it too was cut off mid-word (nothing safe to recover from that).
    if _is_truncated(title):
        return ""
    return title


DESCRIPTION_SIMILARITY_THRESHOLD = 0.55

# A topic-only label is worse than no label: it tells the video generator
# nothing about the individual image and can result in a caption that is
# unrelated to what is actually visible.  Keep a small set of generic words
# out of the specificity check so descriptions must contribute some detail
# beyond merely repeating the search topic.
DESCRIPTION_GENERIC_WORDS = {
    "a", "an", "and", "are", "at", "be", "by", "for", "from", "in", "is",
    "of", "on", "or", "the", "to", "with", "about", "related", "photo",
    "photograph", "picture", "image", "shows", "showing", "depicts", "scene",
    "view", "vintage", "historic", "historical", "old", "classic", "premium",
    "inside", "see", "more", "than", "years", "back", "this", "that",
}


def is_photo_specific_description(description: str, topic: str) -> bool:
    """Return whether *description* says something about this individual photo.

    Search-result titles frequently repeat only the query (for example,
    ``Old school classrooms``).  That is useful for finding an image but not
    for explaining what is in it.  A valid stored description therefore needs
    at least two meaningful words beyond the topic itself and cannot use the
    former generic fallback wording.
    """
    description = (description or "").strip()
    if not description:
        return False
    if re.fullmatch(r"A photo related to .+\.?", description, flags=re.IGNORECASE):
        return False

    topic_words = _topic_keywords(topic)
    words = re.findall(r"[A-Za-z0-9]+", description.lower())
    detail_words = {
        word for word in words
        if len(word) >= 3 and word not in topic_words and word not in DESCRIPTION_GENERIC_WORDS
    }
    return len(detail_words) >= 2


def _normalize_for_similarity(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _description_similarity(a: str, b: str) -> float:
    na, nb = _normalize_for_similarity(a), _normalize_for_similarity(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    seq_ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    union = ta | tb
    jaccard = (len(ta & tb) / float(len(union))) if union else 0.0
    return max(seq_ratio, jaccard)


def find_reused_description(description: str, used_descriptions: list):
    """Safety net for the gallery-page mismatch problem: if this description
    is near-identical to one already used for a *different* photo earlier in
    this run, it's very likely describing the wrong image (e.g. two photos
    from the same multi-photo listicle page ended up with the same reused
    caption). Returns True if a near-duplicate is found.
    """
    for prior in used_descriptions:
        if _description_similarity(description, prior) >= DESCRIPTION_SIMILARITY_THRESHOLD:
            return True
    return False


def resolve_description_text(topic: str, title: str, source_url: str, image_url: str = None,
                              is_gallery_page: bool = False) -> str:
    """Return a clean, complete-sentence description (1-2 sentences) for the
    info file: never containing the source link or publication/credit
    references, never a bare section label like "Opinion.", never ending in
    a dangling '...', and never built from text that has nothing to do with
    the search topic (e.g. a link-aggregator page whose title/body describes
    a completely unrelated subject).

    is_gallery_page should be True when source_url is shared by multiple
    different downloaded photos this run (a listicle/gallery page) -- see
    generate_interesting_description / _heuristic_description for why that
    matters (prevents describing the wrong photo from the same page).
    """
    raw_title = (title or "").strip()

    # Wallpaper/background-download sites and link-aggregator "suggestions"
    # pages never have real editorial text about the specific photo -- their
    # title/body describes the site's wallpaper collection, or (for
    # aggregators) can be about a completely different topic entirely.
    # Skip fetching their page content outright, same as social platforms.
    skip_page_fetch = (
        _is_social_platform_url(source_url)
        or _is_wallpaper_host_url(source_url)
        or _is_link_aggregator_url(source_url)
    )
    page = None if skip_page_fetch else fetch_page_content(source_url, image_url)

    topic_keywords = _topic_keywords(topic)
    image_caption = page.get("image_caption") if page else None

    # A caption tied specifically to this exact <img> tag is trustworthy
    # regardless of the overall page's topic (it directly describes this
    # photo). Everything else -- the raw title, meta description, and body
    # paragraphs -- must share real keywords with the search topic, or it's
    # discarded as untrustworthy/unrelated content (e.g. an aggregator page
    # title about a totally different subject).
    if not image_caption:
        if not _text_matches_topic(raw_title, topic_keywords):
            raw_title = ""
        if page:
            if not _text_matches_topic(page.get("meta_description", ""), topic_keywords):
                page["meta_description"] = ""
            page["paragraphs"] = [
                p for p in page.get("paragraphs", []) if _text_matches_topic(p, topic_keywords)
            ]

    description = generate_interesting_description(topic, raw_title, page, is_gallery_page)
    if not description:
        description = _heuristic_description(raw_title, page, is_gallery_page)

    description = _strip_credit_lines(description)
    description = _trim_to_last_complete_sentence(description) or description.strip()
    description = _strip_unbalanced_quote(description)

    if _is_junk_line(description) or not _text_matches_topic(description, topic_keywords):
        # Last-resort fallback so we never write an empty/junk-only/off-topic
        # line. Never reuse the raw title unchecked here -- it may itself be
        # junk or off-topic (e.g. a YouTube channel name, or an unrelated
        # aggregator-page title).
        fallback_title = _first_title_segment(raw_title)
        if (
            _is_truncated(fallback_title)
            or _is_junk_line(fallback_title)
            or not _text_matches_topic(fallback_title, topic_keywords)
        ):
            fallback_title = ""
        description = fallback_title

    if description and not re.search(r"[.!?]$", description):
        description += "."
    return description


def search_images(topic: str, count: int):
    """Query DuckDuckGo/Bing image search (via ddgs) and return raw result
    dicts, minus watermarked stock sources.

    A single search call caps out at roughly 35 results no matter how large
    max_results is set -- that's a limit of the underlying search backend,
    not something this script can raise directly. To gather enough candidates
    for larger --count requests, we instead request successive result pages
    and merge the new (non-duplicate) results together, stopping once we
    have a comfortable oversupply, a page returns nothing new, or a safety
    page-count cap is hit (to avoid hammering the search backend forever on
    a niche topic that has run out of results).
    """
    target = max(count * 3, 60)
    max_pages = 20

    results = []
    seen_urls = set()

    with DDGS() as ddgs:
        page = 1
        while len(results) < target and page <= max_pages:
            try:
                batch = ddgs.images(topic, max_results=200, page=page)
            except Exception as e:
                print(f"  [WARN] image search page {page} failed: {e}")
                break

            if not batch:
                break

            new_count = 0
            for r in batch:
                image_url = r.get("image")
                if not image_url or image_url in seen_urls:
                    continue
                seen_urls.add(image_url)
                if is_watermarked_stock_source(image_url, r.get("url"), r.get("source")):
                    continue
                results.append(r)
                new_count += 1

            if new_count == 0:
                # This page had nothing we hadn't already seen -- the search
                # backend has run out of distinct results for this topic.
                break

            page += 1

    return results


def download_images(topic: str, count: int, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    slug = slugify(topic)
    info_path = outdir / "info.txt"

    candidates = search_images(topic, count)
    if not candidates:
        print("No results found for that topic.")
        return []

    # A source URL that appears more than once across the candidate pool is a
    # multi-photo gallery/listicle page (e.g. "45 vintage photos of X") --
    # its generic body text can describe any one of many different photos,
    # so it needs extra caution in resolve_description_text (see is_gallery_page).
    source_url_counts = Counter(
        (c.get("url") or c.get("source") or "") for c in candidates
    )

    headers = {"User-Agent": "Mozilla/5.0 (compatible; ImageTopicScraper/1.0)"}

    saved = []
    info_lines = []
    used_descriptions = []  # every accepted description this run (mismatch safety net)
    seen_images = []  # exact_hash/dhash of every image saved so far this run
    n = 0
    # Start with a fresh, empty info file -- it's rewritten after every saved
    # image (not just at the end) so progress is never lost if the run is
    # interrupted partway through a large --count.
    info_path.write_text("", encoding="utf-8")

    for item in candidates:
        if len(saved) >= count:
            break

        image_url = item.get("image")
        if not image_url:
            continue

        # Safety-net check in case a stock/agency link slipped through the
        # first filter (e.g. hotlinked via a different source field).
        if is_watermarked_stock_source(image_url, item.get("url"), item.get("source")):
            print(f"Skipping watermarked stock source: {image_url}")
            continue

        try:
            resp = requests.get(image_url, headers=headers, timeout=15)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "image" not in content_type and not image_url.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp", ".gif")
            ):
                continue

            duplicate_reason = find_duplicate(resp.content, seen_images)
            if duplicate_reason:
                print(f"Skipping {duplicate_reason}: {image_url}")
                continue

            title = _fix_text_encoding(unescape((item.get("title") or "").strip())) or f"Image related to '{topic}'"
            source = item.get("url") or item.get("source") or ""
            is_gallery_page = source_url_counts.get(source, 0) > 1

            description = resolve_description_text(topic, title, source, image_url, is_gallery_page)

            if find_reused_description(description, used_descriptions):
                # This description is near-identical to one already used for
                # a different photo.  It likely belongs to a different image
                # in a gallery, so do not retain the image with a generic
                # substitute caption.
                print("Skipping image: description matched an earlier entry (likely wrong-photo caption)")
                continue

            if not is_photo_specific_description(description, topic):
                print("Skipping image: no reliable photo-specific description available")
                continue

            n += 1
            ext = guess_extension(image_url, content_type)
            filename = f"{slug}--{n}{ext}"
            filepath = outdir / filename
            with open(filepath, "wb") as f:
                f.write(resp.content)

            seen_images.append({
                "exact_hash": compute_exact_hash(resp.content),
                "dhash": compute_dhash(resp.content),
            })

            used_descriptions.append(description)
            info_lines.append(f"{n} | {description}")
            saved.append(filename)
            # Rewrite info.txt after every image (cheap for a text file this
            # small) so progress survives even if the run is interrupted.
            info_path.write_text(
                "\n".join(info_lines) + ("\n" if info_lines else ""), encoding="utf-8"
            )
            print(f"Saved {filename}  ({description[:60]})")
            time.sleep(0.3)  # be polite to the server

        except Exception as e:
            print(f"Skipping {image_url}: {e}")
            continue

    print(f"\nDone. {len(saved)} images saved to '{outdir}', info in '{info_path}'.")
    return saved


def main():
    parser = argparse.ArgumentParser(description="Search and download topic images with a linked info file.")
    parser.add_argument("topic", help="Topic to search for, e.g. 'Miami 1970s photos'")
    parser.add_argument("--count", type=int, default=10, help="Number of images to download (default 10)")
    parser.add_argument("--outdir", type=str, default=None, help="Output folder (default: slug of topic)")
    args = parser.parse_args()

    outdir = Path(args.outdir) if args.outdir else Path(slugify(args.topic))
    download_images(args.topic, args.count, outdir)


if __name__ == "__main__":
    main()
