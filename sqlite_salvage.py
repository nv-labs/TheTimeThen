import sqlite3,traceback,sys
src=r'D:\Dev\TheTimeThen\google_takeout_photos_2023.db.copy'
dst=r'D:\Dev\TheTimeThen\google_takeout_photos_2023.salvaged.db'
print('Opening source:', src)
try:
    sconn=sqlite3.connect(src)
    scur=sconn.cursor()
    tables = scur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    print('Found tables:', [t[0] for t in tables])
except Exception as e:
    print('ERROR reading schema:', e)
    traceback.print_exc()
    sys.exit(1)

# create dst
dconn=sqlite3.connect(dst)
dcur=dconn.cursor()
recovered = 0
for name, sql in tables:
    try:
        print('\nProcessing table:', name)
        # create table in dst
        try:
            dcur.execute(sql)
            dconn.commit()
        except Exception as e:
            print('Could not create table with original SQL, attempting generic create:', e)
            # fallback: create table with same columns
            cols = scur.execute(f"PRAGMA table_info({name})").fetchall()
            col_defs = ','.join([f'"{c[1]}" {c[2] or "BLOB"}' for c in cols])
            dcur.execute(f'CREATE TABLE IF NOT EXISTS "{name}" ({col_defs})')
            dconn.commit()
        # try to get max rowid
        try:
            max_rowid = scur.execute(f"SELECT MAX(rowid) FROM \"{name}\"").fetchone()[0] or 0
        except Exception:
            max_rowid = 0
        print('Estimated max rowid:', max_rowid)
        if max_rowid == 0:
            # fallback: try simple select
            try:
                rows = scur.execute(f'SELECT * FROM "{name}"').fetchall()
                if rows:
                    placeholders = ','.join(['?'] * len(rows[0]))
                    ins = f'INSERT INTO "{name}" VALUES ({placeholders})'
                    dcur.executemany(ins, rows)
                    dconn.commit()
                    recovered += len(rows)
                    print('Recovered', len(rows), 'rows')
                continue
            except Exception as e:
                print('No rows or select failed:', e)
                continue
        # iterate rowids
        cols = scur.execute(f"PRAGMA table_info(\"{name}\")").fetchall()
        col_count = len(cols)
        placeholders = ','.join(['?'] * col_count)
        ins = f'INSERT INTO "{name}" VALUES ({placeholders})'
        recovered_table = 0
        for rid in range(1, max_rowid+1):
            try:
                row = scur.execute(f'SELECT * FROM "{name}" WHERE rowid=?', (rid,)).fetchone()
                if row:
                    # ensure row has correct length
                    if len(row) != col_count:
                        # pad or truncate
                        row = tuple(list(row)[:col_count] + [None] * max(0, col_count - len(row)))
                    dcur.execute(ins, row)
                    recovered_table += 1
                    recovered += 1
            except Exception:
                # skip problematic row
                continue
        dconn.commit()
        print('Recovered', recovered_table, 'rows from', name)
    except Exception as e:
        print('Failed table', name, 'error:', e)
        traceback.print_exc()

sconn.close()
dconn.close()
print('\nSalvage complete. Total recovered rows:', recovered)
