import sqlite3
import logging

# -----------------------
# Logging setup
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

DB_PATH = "mydb.db"
TABLE_NAME = "my_table"  # replace with your table name
ROWS_TO_FETCH = 500       # how many rows to check

def peek_database():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_NAME}';")
        if not cursor.fetchone():
            logging.error(f"Table '{TABLE_NAME}' does not exist in database.")
            return

        # Fetch a few rows
        cursor.execute(f"SELECT * FROM {TABLE_NAME} LIMIT {ROWS_TO_FETCH};")
        rows = cursor.fetchall()
        if not rows:
            logging.info("No rows found in the table.")
            return

        # Print rows with their category if column exists
        col_names = [desc[0] for desc in cursor.description]
        logging.info(f"Columns in table: {col_names}")

        for row in rows:
            row_dict = dict(zip(col_names, row))
            # Adjust 'category' to your actual column name
            category = row_dict.get("category", "N/A")
            logging.info(f"Row: {row_dict}, Category: {category}")

    except sqlite3.Error as e:
        logging.error(f"SQLite error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    peek_database()
