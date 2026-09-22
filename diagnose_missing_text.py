import re
from pathlib import Path

base = Path(r'D:\Dev\TheTimeThen\output')

# Load cleaned text IDs
text_ids = {}
with (base / 'extracted_text_cleaned.txt').open('r', encoding='utf-8') as f:
    for line in f:
        m = re.match(r'\s*(\d+)\s*\|\s*(.+)', line)
        if m:
            text_ids[int(m.group(1))] = m.group(2).strip()

# Load image IDs
img_ids = {}
for p in sorted(base.glob('*.png')):
    m = re.search(r'--(\d+)\.png$', p.name)
    if m:
        img_ids[int(m.group(1))] = p.name

# Load raw OCR
raw_ids = {}
raw_path = base / 'centered_extracted_text.txt'
if raw_path.exists():
    with raw_path.open('r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r'\s*(\d+)\s*\|\s*(.+)', line)
            if m:
                raw_ids[int(m.group(1))] = m.group(2).strip()

print(f'Images: {len(img_ids)}, Cleaned: {len(text_ids)}, Raw: {len(raw_ids)}')

missing = sorted(set(img_ids) - set(text_ids))
print(f'\nImages missing from cleaned text ({len(missing)}):')
for idx in missing:
    raw = raw_ids.get(idx, 'NO RAW OCR')
    fname = img_ids[idx]
    print(f'  {idx} | {fname}')
    print(f'       raw: {raw[:120]}')
    print()
