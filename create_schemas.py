import sqlite3
import os

def create_and_migrate_dbs(original_db='universal_image_archive.db', db_name='universal_image_archive'):
    """Creates 10 database schemas and migrates data from the original database."""
    schema_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
    connections = {}

    # Create or connect to the new schemas
    for letter in schema_letters:
        db_file = f'{db_name}_{letter}.db'
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS archived_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                file_data BLOB NOT NULL,
                source_url TEXT NOT NULL UNIQUE,
                file_type TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                video_air_date TEXT,  -- Changed to TEXT to allow empty string
                xml_collection TEXT,
                xml_date TEXT,
                xml_subject TEXT,
                xml_language TEXT,
                xml_title TEXT,
                description TEXT
            )
        ''')
        
        conn.commit()
        connections[letter] = conn
        print(f"Created or connected to schema: {db_file}")

    # Migrate data from the original database
    if os.path.exists(original_db):
        try:
            orig_conn = sqlite3.connect(original_db)
            orig_cursor = orig_conn.cursor()
            
            # Fetch all records from the original database
            orig_cursor.execute('''
                SELECT id, filename, file_size, file_data, source_url, file_type, 
                       added_date, video_air_date, xml_collection, xml_date, 
                       xml_subject, xml_language, xml_title, description 
                FROM archived_files
            ''')
            records = orig_cursor.fetchall()
            
            print(f"Found {len(records)} records in {original_db} to migrate.")

            # Distribute records across the 10 schemas
            for record in records:
                record_id = record[0]  # Use original ID for distribution
                schema_index = record_id % 10  # Distribute based on modulo 10
                schema_letter = schema_letters[schema_index]
                target_conn = connections[schema_letter]
                target_cursor = target_conn.cursor()
                
                # Handle video_air_date: convert NULL to empty string
                video_air_date = record[7] if record[7] is not None else ''
                
                # Insert record into the target schema
                target_cursor.execute('''
                    INSERT OR IGNORE INTO archived_files (
                        filename, file_size, file_data, source_url, file_type, 
                        added_date, video_air_date, xml_collection, xml_date, 
                        xml_subject, xml_language, xml_title, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record[1],  # filename
                    record[2],  # file_size
                    record[3],  # file_data
                    record[4],  # source_url
                    record[5],  # file_type
                    record[6],  # added_date
                    video_air_date,  # video_air_date
                    record[8],  # xml_collection
                    record[9],  # xml_date
                    record[10], # xml_subject
                    record[11], # xml_language
                    record[12], # xml_title
                    record[13]  # description
                ))
              import sqlite3
import os

def create_and_copy_dbs(original_db='universal_image_archive.db', db_name='universal_image_archive'):
    """Creates 10 database schemas and copies data from the original database without modifying it."""
    schema_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
    connections = {}

    # Create or connect to the new schemas
    for letter in schema_letters:
        db_file = f'{db_name}_{letter}.db'
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS archived_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                file_data BLOB NOT NULL,
                source_url TEXT NOT NULL UNIQUE,
                file_type TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                video_air_date TEXT,  -- TEXT to allow empty string
                xml_collection TEXT,
                xml_date TEXT,
                xml_subject TEXT,
                xml_language TEXT,
                xml_title TEXT,
                description TEXT
            )
        ''')
        
        conn.commit()
        connections[letter] = conn
        print(f"Created or connected to schema: {db_file}")

    # Copy data from the original database
    if os.path.exists(original_db):
        try:
            orig_conn = sqlite3.connect(original_db)
            orig_cursor = orig_conn.cursor()
            
            # Check if video_air_date column exists in the original database
            orig_cursor.execute("PRAGMA table_info(archived_files)")
            columns = [info[1] for info in orig_cursor.fetchall()]
            has_video_air_date = 'video_air_date' in columns
            
            # Define the SELECT query based on whether video_air_date exists
            if has_video_air_date:
                select_query = '''
                    SELECT id, filename, file_size, file_data, source_url, file_type, 
                           added_date, video_air_date, xml_collection, xml_date, 
                           xml_subject, xml_language, xml_title, description 
                    FROM archived_files
                '''
            else:
                select_query = '''
                    SELECT id, filename, file_size, file_data, source_url, file_type, 
                           added_date, NULL as video_air_date, xml_collection, xml_date, 
                           xml_subject, xml_language, xml_title, description 
                    FROM archived_files
                '''
            
            # Fetch all records from the original database
            orig_cursor.execute(select_query)
            records = orig_cursor.fetchall()
            
            print(f"Found {len(records)} records in {original_db} to copy.")

            # Distribute records across the 10 schemas
            for record in records:
                record_id = record[0]  # Use original ID for distribution
                schema_index = record_id % 10  # Distribute based on modulo 10
                schema_letter = schema_letters[schema_index]
                target_conn = connections[schema_letter]
                target_cursor = target_conn.cursor()
                
                # Set video_air_date to empty string
                video_air_date = record[7] if has_video_air_date and record[7] is not None else ''
                
                # Insert record into the target schema
                target_cursor.execute('''
                    INSERT OR IGNORE INTO archived_files (
                        filename, file_size, file_data, source_url, file_type, 
                        added_date, video_air_date, xml_collection, xml_date, 
                        xml_subject, xml_language, xml_title, description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record[1],  # filename
                    record[2],  # file_size
                    record[3],  # file_data
                    record[4],  # source_url
                    record[5],  # file_type
                    record[6],  # added_date
                    video_air_date,  # video_air_date
                    record[8],  # xml_collection
                    record[9],  # xml_date
                    record[10], # xml_subject
                    record[11], # xml_language
                    record[12], # xml_title
                    record[13]  # description
                ))
                
                target_conn.commit()
            
            print(f"Copied {len(records)} records across {len(schema_letters)} schemas.")
            orig_conn.close()
            
        except Exception as e:
            print(f"Error during copying: {e}")
        finally:
            if 'orig_conn' in locals():
                orig_conn.close()
    
    else:
        print(f"Original database {original_db} not found. Created empty schemas.")

    # Close all connections
    for conn in connections.values():
        conn.close()

if __name__ == "__main__":
    create_and_copy_dbs()  
                target_conn.commit()
            
            print(f"Migrated {len(records)} records across {len(schema_letters)} schemas.")
            orig_conn.close()
            
        except Exception as e:
            print(f"Error during migration: {e}")
        finally:
            if 'orig_conn' in locals():
                orig_conn.close()
    
    else:
        print(f"Original database {original_db} not found. Created empty schemas.")

    # Close all connections
    for conn in connections.values():
        conn.close()

if __name__ == "__main__":
    create_and_migrate_dbs()