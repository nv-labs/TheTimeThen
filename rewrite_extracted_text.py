import sys
import os
import re
import time
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
    # 1) Prefer explicit environment variable.
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key

    # 2) Fallback: .env next to this script.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.join(script_dir, ".env")
    return _read_dotenv_key(dotenv_path, "OPENAI_API_KEY")


def _get_client():
    global _client
    if _client is None:
        api_key = _resolve_api_key()
        if not api_key:
            raise RuntimeError(
                "Missing OpenAI API key. Set OPENAI_API_KEY or add it to TheTimeThen/.env"
            )
        _client = OpenAI(api_key=api_key)
    return _client



def clean_and_rewrite(text):
    """
    Returns a clean, real English sentence.
    If only location/date survives, return only that.
    If nothing meaningful exists, return empty string.
    """

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

            # Exponential backoff to reduce transient API/network failures.
            delay = RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1))
            print(f"⏳ Retry {attempt}/{MAX_RETRIES - 1} after API error: {e}")
            time.sleep(delay)
    else:
        if last_err:
            raise last_err
        raise RuntimeError("Unknown rewrite failure")

    # Final sanity cleanup
    result = re.sub(r"\s+", " ", result)
    result = result.strip(" .,")

    if len(result) < 4:
        return ""

    return result + "."


def _load_processed_indices(output_path):
    processed = set()
    if not os.path.exists(output_path):
        return processed

    with open(output_path, "r", encoding="utf-8") as outfile:
        for line in outfile:
            m = re.match(r"(\d+)\s*\|", line.strip())
            if m:
                processed.add(m.group(1))

    return processed


def process_file(input_path):
    if not os.path.exists(input_path):
        print("❌ File not found:", input_path)
        return

    output_path = os.path.join(
        os.path.dirname(input_path),
        "extracted_text_cleaned.txt"
    )

    # Validate API access once so we do not emit a failure per line.
    try:
        _get_client()
    except Exception as e:
        print(f"❌ rewrite setup failed: {e}")
        return

    processed_indices = _load_processed_indices(output_path)
    mode = "a" if os.path.exists(output_path) else "w"

    with open(input_path, "r", encoding="utf-8") as infile, \
         open(output_path, mode, encoding="utf-8") as outfile:

        for line in infile:
            line = line.strip()
            if not line:
                continue

            match = re.match(r"(\d+)\s*\|\s*(.+)", line)
            if not match:
                continue

            index, text = match.groups()

            if index in processed_indices:
                print(f"↪️ Skipping line {index} (already cleaned)")
                continue

            try:
                cleaned = clean_and_rewrite(text)

                if cleaned:
                    outfile.write(f"{index} | {cleaned}\n")
                    outfile.flush()
                    processed_indices.add(index)
                    print(f"✅ Cleaned line {index}")
                else:
                    print(f"⚠️ Skipped line {index} (no real content)")

                time.sleep(SLEEP_SEC)

            except Exception as e:
                print(f"❌ Failed line {index}: {e}")

    print("\n🎉 DONE")
    print("📄 Output file:", output_path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage:")
        print('python rewrite_extracted_text.py "C:\\path\\to\\extracted_text.txt"')
        sys.exit(1)

    process_file(sys.argv[1])
