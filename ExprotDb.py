import sqlite3
import pandas as pd

def export_to_csv(db_name='universal_image_archive.db', output_csv='archived_files_export.csv'):
    """Export the archived_files table to a CSV file, excluding the file_data column."""
    try:
        conn = sqlite3.connect(db_name)
        # Query all columns except file_data (BLOB) to avoid issues with CSV
        query = '''
            SELECT id, filename, file_size, source_url, file_type, added_date,
                   xml_collection, xml_date, xml_subject, xml_language, xml_title,
                   description, VideoAirDate
            FROM archived_files
        '''
        df = pd.read_sql_query(query, conn)
        df.to_csv(output_csv, index=False, encoding='utf-8')
        print(f"Successfully exported database to '{output_csv}'")
    except Exception as e:
        print(f"Error exporting to CSV: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export_to_csv()