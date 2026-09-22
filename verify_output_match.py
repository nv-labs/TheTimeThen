import re
import time
from pathlib import Path

base = Path(r'D:\Dev\TheTimeThen\output')
text_path = base / 'extracted_text_cleaned.txt'


def load_text_ids():
    ids = []
    if text_path.exists():
        with text_path.open('r', encoding='utf-8') as f:
            for line in f:
                m = re.match(r'\s*(\d+)\s*\|', line)
                if m:
                    ids.append(int(m.group(1)))
    return ids

while True:
    text_ids = load_text_ids()
    img_ids = []
    for p in sorted(base.glob('*.png')):
        m = re.search(r'--(\d+)\.png$', p.name)
        if m:
            img_ids.append(int(m.group(1)))

    text_set = set(text_ids)
    img_set = set(img_ids)
    missing_in_images = sorted(text_set - img_set)
    missing_in_text = sorted(img_set - text_set)
    text_dupes = sorted({x for x in text_ids if text_ids.count(x) > 1})
    img_dupes = sorted({x for x in img_ids if img_ids.count(x) > 1})

    print(f'[{time.strftime("%H:%M:%S")}] text={len(text_ids)} images={len(img_ids)} | missing_in_images={missing_in_images[:10]} | missing_in_text={missing_in_text[:10]} | text_dupes={text_dupes[:10]} | img_dupes={img_dupes[:10]}')
    time.sleep(30)
