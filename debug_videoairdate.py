import sqlite3

output = []

# Check DB1
output.append('=== DB1: photos_2023_photos ===')
try:
    conn = sqlite3.connect('universal_image_archive.db')
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(photos_2023_photos)')
    cols = [r[1] for r in cur.fetchall()]
    output.append(f'Columns: {cols}')

    # Get all VideoAirDate values
    cur.execute('SELECT COUNT(*) FROM photos_2023_photos WHERE VideoAirDate IS NOT NULL AND VideoAirDate != ""')
    count = cur.fetchone()[0]
    output.append(f'Non-null VideoAirDate rows: {count}')

    # Show recent VideoAirDate values to see what date range exists
    cur.execute('SELECT id, VideoAirDate FROM photos_2023_photos WHERE VideoAirDate IS NOT NULL AND VideoAirDate != "" ORDER BY VideoAirDate DESC LIMIT 10')
    output.append('\nMost recent VideoAirDate values in DB1:')
    for row in cur.fetchall():
        output.append(f'  id={row[0]}, VideoAirDate={row[1]}')

    conn.close()
except Exception as e:
    output.append(f'DB1 Error: {e}')

# Check DB2
output.append('\n=== DB2: image_comp ===')
try:
    conn = sqlite3.connect('image_collection.db')
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(image_comp)')
    cols = [r[1] for r in cur.fetchall()]
    output.append(f'Columns: {cols}')

    cur.execute('SELECT COUNT(*) FROM image_comp WHERE VideoAirDate IS NOT NULL AND VideoAirDate != ""')
    count = cur.fetchone()[0]
    output.append(f'Non-null VideoAirDate rows: {count}')

    # Show recent VideoAirDate values
    cur.execute('SELECT id, VideoAirDate FROM image_comp WHERE VideoAirDate IS NOT NULL AND VideoAirDate != "" ORDER BY VideoAirDate DESC LIMIT 10')
    output.append('\nMost recent VideoAirDate values in DB2:')
    for row in cur.fetchall():
        output.append(f'  id={row[0]}, VideoAirDate={row[1]}')

    conn.close()
except Exception as e:
    output.append(f'DB2 Error: {e}')

with open('debug_output.txt', 'w') as f:
    f.write('\n'.join(output))

print('\n'.join(output))
