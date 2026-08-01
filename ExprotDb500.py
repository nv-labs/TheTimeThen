import sqlite3
import csv
import time
import random

def export_to_csv(db_name='universal_image_archive.db', output_csv='archived_files_export.csv', limit=50):
    """Export up to 50 randomly selected rows from the archived_files table to a CSV file, excluding the file_data column."""
    start_time = time.time()
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        
        # Optimize SQLite settings
        cursor.execute("PRAGMA synchronous = OFF;")  # Disable sync for faster writes
        cursor.execute("PRAGMA journal_mode = MEMORY;")  # Use in-memory journal
        cursor.execute("PRAGMA cache_size = 10000;")  # Increase cache size
        
        # Get min and max id for random selection
        query_time = time.time()
        cursor.execute("SELECT MIN(id), MAX(id) FROM archived_files")
        min_id, max_id = cursor.fetchone()
        print(f"Retrieved ID range ({min_id}, {max_id}) in {time.time() - query_time:.2f} seconds")
        
        # Generate random IDs
        random_ids = random.sample(range(min_id, max_id + 1), min(limit, max_id - min_id + 1))
        
        # Query specific rows by ID
        query_time = time.time()
        query = '''
            SELECT id, filename, file_size, source_url, file_type, added_date,
                   xml_collection, xml_date, xml_subject, xml_language, xml_title,
                   description, VideoAirDate
            FROM archived_files
            WHERE id IN ({})
            LIMIT ?
        '''.format(','.join('?' * len(random_ids)))
        cursor.execute(query, random_ids + [limit])
        
        # Fetch column names
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        row_count = len(rows)
        print(f"Retrieved {row_count} rows from the database in {time.time() - query_time:.2f} seconds")
        
        # Write directly to CSV
        write_time = time.time()
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(columns)  # Write header
            writer.writerows(rows)   # Write data rows
        print(f"Exported {row_count} rows to '{output_csv}' in {time.time() - write_time:.2f} seconds")
        
        print(f"Total execution time: {time.time() - start_time:.2f} seconds")
        
    except Exception as e:
        print(f"Error exporting to CSV: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export_to_csv()