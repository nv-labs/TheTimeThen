import sqlite3

def copy_photos_to_new_db():
    try:
        # Connect to the original database
        original_conn = sqlite3.connect('universal_image_archive.db')
        original_cursor = original_conn.cursor()

        # Check if the photos table exists
        original_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='photos'")
        if not original_cursor.fetchone():
            print("❌ Error: Table 'photos' does not exist in 'universal_image_archive.db'.")
            return

        # Create a new database
        new_conn = sqlite3.connect('image_collection.db')
        new_cursor = new_conn.cursor()

        # Create the new table image_comp with the same structure
        new_cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_comp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_size INTEGER,
                file_data BLOB NOT NULL,
                source_url TEXT,
                file_type TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                xml_title TEXT,
                description TEXT,
                xml_subject TEXT
            )
        """)

        # Select all rows from the original table
        original_cursor.execute("""
            SELECT filename, file_size, file_data, source_url, file_type, added_date, xml_title, description, xml_subject 
            FROM photos
        """)
        rows = original_cursor.fetchall()

        # Insert all rows into the new table
        if rows:
            new_cursor.executemany("""
                INSERT INTO image_comp (filename, file_size, file_data, source_url, file_type, added_date, xml_title, description, xml_subject)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            new_conn.commit()
            print(f"🎉 Success! Inserted {len(rows)} rows into 'image_comp' table in 'image_collection.db'.")
        else:
            print("⚠️ No rows found in 'photos' table. Nothing to insert.")

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    finally:
        # Close connections
        if 'original_conn' in locals():
            original_conn.close()
        if 'new_conn' in locals():
            new_conn.close()

if __name__ == "__main__":
    copy_photos_to_new_db()