"""
fix_missing_text.py
For every image in output/ that has no entry in extracted_text_cleaned.txt,
add a cleaned entry using:
  1. OpenAI rewrite of the raw OCR (if available and meaningful)
  2. A sensible fallback derived from the raw OCR tokens
  3. Delete orphan image files whose raw OCR is only "image" (no real content)

Usage: python fix_missing_text.py [--dry-run] [--no-delete-blanks]
"""
import re
import os
import sys
import time
from pathlib import Path
from difflib import SequenceMatcher

DRY_RUN = '--dry-run' in sys.argv
NO_DELETE = '--no-delete-blanks' in sys.argv

BASE = Path(r'D:\Dev\TheTimeThen\output')
CLEANED = BASE / 'extracted_text_cleaned.txt'
RAW = BASE / 'centered_extracted_text.txt'

# ── helpers ──────────────────────────────────────────────────────────────────

def load_entries(path):
    """Return {id: text} dict, preserving order."""
    d = {}
    if not path.exists():
        return d
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r'\s*(\d+)\s*\|\s*(.+)', line)
            if m:
                d[int(m.group(1))] = m.group(2).strip()
    return d


def save_entries(path, d):
    """Write sorted {id: text} to file."""
    with path.open('w', encoding='utf-8') as f:
        for idx in sorted(d):
            f.write(f'{idx} | {d[idx]}\n')


def is_blank_raw(raw_text):
    stripped = raw_text.strip().lower()
    return stripped in ('image', '', 'none')


def quick_clean(raw_text):
    """Simple rule-based cleaning when OpenAI is not available."""
    # strip obvious OCR noise: runs of symbols, short tokens
    tokens = raw_text.split()
    good = []
    for t in tokens:
        clean = re.sub(r'[^a-zA-Z0-9\'.,;:()\-]', '', t)
        if len(clean) >= 2 and re.search(r'[a-zA-Z]', clean):
            good.append(clean)
    return ' '.join(good)


def openai_clean(raw_text):
    try:
        from openai import OpenAI
        import dotenv
        dotenv.load_dotenv(Path(__file__).parent / '.env')
        api_key = os.getenv('OPENAI_API_KEY', '').strip()
        if not api_key:
            return None
        client = OpenAI(api_key=api_key)
        prompt = (
            "You are cleaning OCR text from historical photo captions.\n"
            "Rules:\n"
            "- Remove all OCR garbage, symbols, broken words\n"
            "- Keep ONLY real English words\n"
            "- Preserve names of people, places, and years exactly\n"
            "- Do NOT invent facts\n"
            "- Output ONE clean sentence or phrase\n"
            "- If nothing meaningful, output NOTHING\n\n"
            f"OCR Text:\n{raw_text}\n\nOutput:"
        )
        r = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.2,
            timeout=30,
        )
        result = (r.choices[0].message.content or '').strip().strip(' .,')
        if len(result) < 4:
            return None
        if not result.endswith('.'):
            result += '.'
        return result
    except Exception as e:
        print(f'  [WARN] OpenAI failed: {e}')
        return None


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    text_ids = load_entries(CLEANED)
    raw_ids = load_entries(RAW)

    img_ids = {}
    for p in sorted(BASE.glob('*.png')):
        m = re.search(r'--(\d+)\.png$', p.name)
        if m:
            img_ids[int(m.group(1))] = p

    missing = sorted(set(img_ids) - set(text_ids))
    print(f'Total images: {len(img_ids)}, Cleaned entries: {len(text_ids)}, Missing: {len(missing)}')

    blanks = []
    to_add = {}

    for idx in missing:
        raw = raw_ids.get(idx, 'image')
        fname = img_ids[idx].name

        if is_blank_raw(raw):
            blanks.append(idx)
            print(f'  BLANK  {idx} | {fname}')
            continue

        print(f'  FIX    {idx} | {fname}')
        print(f'         raw: {raw[:100]}')

        if not DRY_RUN:
            cleaned = openai_clean(raw)
            if not cleaned:
                cleaned = quick_clean(raw)
                if len(cleaned) < 6:
                    cleaned = f'Historical photo #{idx}.'
                elif not cleaned.endswith('.'):
                    cleaned += '.'
            print(f'         -> {cleaned}')
            to_add[idx] = cleaned
            time.sleep(0.4)
        else:
            print(f'         [DRY RUN] would add cleaned entry')

    # Delete blank-image files
    if blanks and not NO_DELETE:
        print(f'\nDeleting {len(blanks)} blank image files...')
        for idx in blanks:
            p = img_ids[idx]
            if not DRY_RUN:
                p.unlink()
                print(f'  DELETED {p.name}')
            else:
                print(f'  [DRY RUN] would delete {p.name}')

    # Write updated cleaned file
    if to_add and not DRY_RUN:
        text_ids.update(to_add)
        save_entries(CLEANED, text_ids)
        print(f'\nSaved {len(text_ids)} entries to {CLEANED}')

    # Final verification
    if not DRY_RUN:
        text_ids2 = load_entries(CLEANED)
        img_ids2 = {}
        for p in sorted(BASE.glob('*.png')):
            m = re.search(r'--(\d+)\.png$', p.name)
            if m:
                img_ids2[int(m.group(1))] = p.name
        still_missing = sorted(set(img_ids2) - set(text_ids2))
        print(f'\n=== FINAL CHECK ===')
        print(f'Images: {len(img_ids2)}, Cleaned: {len(text_ids2)}, Still missing: {len(still_missing)}')
        if still_missing:
            print(f'Missing: {still_missing}')
        else:
            print('OK: Every image has a matching text entry.')


if __name__ == '__main__':
    main()
