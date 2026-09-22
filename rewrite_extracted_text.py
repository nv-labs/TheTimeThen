import os
import re
import sys
import time
from difflib import SequenceMatcher

from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, APIError

# ================= CONFIG =================
MODEL = "gpt-4o-mini"
TEMPERATURE = 0.2
SLEEP_SEC = 0.4
REQUEST_TIMEOUT_SEC = 45
MAX_RETRIES = 3
RETRY_BASE_DELAY_SEC = 1.5
# ========================================

_client = None


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


def _resolve_api_key():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key

    script_dir = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.join(script_dir, ".env")
    return _read_dotenv_key(dotenv_path, "OPENAI_API_KEY")


def _get_client():
    global _client
    if _client is None:
        api_key = _resolve_api_key()
        if not api_key:
            raise RuntimeError("Missing OpenAI API key. Set OPENAI_API_KEY or add it to TheTimeThen/.env")
        _client = OpenAI(api_key=api_key)
    return _client


def _normalize_cleaned_text(text):
    if not text:
        return ""
    normalized = text.lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _cleaned_similarity(a, b):
    na = _normalize_cleaned_text(a)
    nb = _normalize_cleaned_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    seq_ratio = SequenceMatcher(None, na, nb).ratio()
    ta = set(na.split())
    tb = set(nb.split())
    union = ta | tb
    jaccard = (len(ta & tb) / float(len(union))) if union else 0.0
    return max(seq_ratio, jaccard)


def _is_near_duplicate_cleaned(candidate_text, existing_texts, threshold=0.90):
    candidate_norm = _normalize_cleaned_text(candidate_text)
    if not candidate_norm:
        return False

    stop = {"a", "an", "the", "in", "on", "of", "and", "to", "from", "with", "at", "is", "was", "are"}
    cand_tokens = {tok for tok in candidate_norm.split() if tok not in stop and len(tok) > 2}
    cand_years = set(re.findall(r"(?:18|19|20)\d{2}", candidate_norm))

    for existing in existing_texts:
        existing_norm = _normalize_cleaned_text(existing)
        if not existing_norm:
            continue

        sim = _cleaned_similarity(candidate_norm, existing_norm)
        if sim >= threshold:
            return True

        shorter, longer = (candidate_norm, existing_norm) if len(candidate_norm) <= len(existing_norm) else (existing_norm, candidate_norm)
        if len(shorter) >= 12 and shorter in longer:
            return True

        if sim >= 0.76:
            return True

        existing_tokens = {tok for tok in existing_norm.split() if tok not in stop and len(tok) > 2}
        existing_years = set(re.findall(r"(?:18|19|20)\d{2}", existing_norm))
        if cand_years and existing_years and (cand_years & existing_years):
            if len(cand_tokens & existing_tokens) >= 2:
                if len(cand_tokens) <= 7 or len(existing_tokens) <= 7:
                    return True

    return False

def _parse_output_line(line):
    m = re.match(r"(\d+)\s*\|\s*(.+)", line.strip())
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _compact_existing_output(output_path):
    if not os.path.exists(output_path):
        return set(), []

    with open(output_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    kept_lines = []
    processed_indices = set()
    changed = False

    for raw in lines:
        index, cleaned = _parse_output_line(raw)
        if index is None:
            changed = True
            continue
        if index in processed_indices:
            changed = True
            continue

        kept_lines.append(f"{index} | {cleaned}\n")
        processed_indices.add(index)

    if changed:
        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(kept_lines)

    cleaned_history = [line.split("|", 1)[1].strip() for line in kept_lines]
    return processed_indices, cleaned_history


def clean_and_rewrite(text):
    prompt = f"""
You are cleaning OCR text from historical photo captions.

Rules (VERY IMPORTANT):
- Remove all OCR garbage, symbols, broken words
- Keep ONLY real English words
- Preserve names of people, places, and years exactly
- Do NOT invent facts
- If only a location and/or year is meaningful, output ONLY that
- Output ONE clean sentence or phrase
- If nothing meaningful exists, output NOTHING

OCR Text:
{text}

Output:
"""

    last_err = None
    client = _get_client()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                timeout=REQUEST_TIMEOUT_SEC,
            )
            result = (response.choices[0].message.content or "").strip()
            break
        except (APITimeoutError, APIConnectionError, RateLimitError, APIError) as e:
            last_err = e
            if attempt == MAX_RETRIES:
                raise

            delay = RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1))
            print(f"Retry {attempt}/{MAX_RETRIES - 1} after API error: {e}")
            time.sleep(delay)
    else:
        if last_err:
            raise last_err
        raise RuntimeError("Unknown rewrite failure")

    result = re.sub(r"\s+", " ", result)
    result = result.strip(" .,")

    if len(result) < 4:
        return ""

    return result + "."


def process_file(input_path):
    if not os.path.exists(input_path):
        print("File not found:", input_path)
        return

    output_path = os.path.join(os.path.dirname(input_path), "extracted_text_cleaned.txt")

    try:
        _get_client()
    except Exception as e:
        print(f"rewrite setup failed: {e}")
        return

    processed_indices, cleaned_history = _compact_existing_output(output_path)

    with open(input_path, "r", encoding="utf-8") as infile, open(output_path, "a", encoding="utf-8") as outfile:
        for line in infile:
            line = line.strip()
            if not line:
                continue

            match = re.match(r"(\d+)\s*\|\s*(.+)", line)
            if not match:
                continue

            index, text = match.groups()
            if index in processed_indices:
                print(f"Skipping line {index} (already cleaned)")
                continue

            try:
                cleaned = clean_and_rewrite(text)
                if not cleaned:
                    print(f"Skipped line {index} (no real content)")
                    time.sleep(SLEEP_SEC)
                    continue

                outfile.write(f"{index} | {cleaned}\n")
                outfile.flush()
                processed_indices.add(index)
                cleaned_history.append(cleaned)
                print(f"Cleaned line {index}")
                time.sleep(SLEEP_SEC)
            except Exception as e:
                print(f"Failed line {index}: {e}")

    print("DONE")
    print("Output file:", output_path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:")
        print('python rewrite_extracted_text.py "C:\\path\\to\\extracted_text.txt"')
        sys.exit(1)

    process_file(sys.argv[1])