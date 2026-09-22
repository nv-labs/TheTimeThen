import re
from pathlib import Path

CLEANED = Path(r'D:\Dev\TheTimeThen\output\extracted_text_cleaned.txt')

correct = {
    5: 'Nancy Wake, nicknamed "The White Mouse," SOE agent who led Resistance fighters in Occupied France during WWII, 1944.',
    12: 'Parking at the Grand Canyon, 1914.',
    17: 'Home, carved from a 14-foot wide cedar stump; used as shelter until a proper house was built, 1901.',
    18: 'Home, carved from a 14-foot wide cedar stump; used as a shelter until a proper house was built.',
    23: 'Reza Pahlavi, Iranian exiled crown prince and opposition leader, during his training at Reese AFB in Lubbock, Texas, 1978.',
    27: 'Nellie Brown, a cowgirl from the 1880s.',
    31: 'Early tourists pose on Glacier Point above the Yosemite Valley, 1887.',
    50: 'Crowd of depositors gather in the rain outside Bank of United States after its failure (1931).',
    51: 'Crowd of depositors gather in the rain outside Bank of United States after its failure (1931).',
    58: 'Worker at pasta factory inspecting spaghetti. Photo by Alfred Eisenstaedt, 1932.',
    59: 'Worker at pasta factory inspecting spaghetti in drying room. Photo by Alfred Eisenstaedt, 1932.',
    63: 'A woman riding on a Snow King Chairlift, 1960s.',
    65: 'Arnaldo Tamayo Mendez, The First Black Man in Space (1980).',
    69: 'Carrie Fisher and Darth Vader, 1983.',
    76: 'Dean Martin and Angie Dickinson behind the scenes on the set of Rio Bravo, 1959.',
    81: 'Two women sitting on a rustic countryside bench, around 1972.',
    83: 'Consolidated PB4Y-2 Privateer on fire over Singapore, 1945.',
    84: 'Consolidated PB4Y-2 Privateer on fire over Singapore, 1945.',
}

entries = {}
with CLEANED.open('r', encoding='utf-8') as f:
    for line in f:
        m = re.match(r'\s*(\d+)\s*\|\s*(.+)', line)
        if m:
            entries[int(m.group(1))] = m.group(2).strip()

for idx, text in correct.items():
    entries[idx] = text

with CLEANED.open('w', encoding='utf-8') as f:
    for idx in sorted(entries):
        f.write(f'{idx} | {entries[idx]}\n')

print(f'Saved {len(entries)} entries.')
for idx in sorted(correct):
    print(f'  {idx} | {entries[idx]}')
