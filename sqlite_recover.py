import sqlite3,sys,traceback
src=r'D:\Dev\TheTimeThen\google_takeout_photos_2023.db.copy'
dump_path=r'D:\Dev\TheTimeThen\google_takeout_photos_2023.dump.sql'
dst=r'D:\Dev\TheTimeThen\google_takeout_photos_2023.recovered.db'
try:
    conn=sqlite3.connect(src)
    with open(dump_path,'w',encoding='utf-8') as f:
        for line in conn.iterdump():
            f.write(line + '\n')
    conn.close()
    # Now import into new DB
    dst_conn=sqlite3.connect(dst)
    with open(dump_path,'r',encoding='utf-8') as f:
        sql = f.read()
    dst_conn.executescript(sql)
    dst_conn.close()
    print('RECOVERY_OK')
except Exception as e:
    traceback.print_exc()
    print('RECOVERY_FAILED')
    sys.exit(1)
