import sqlite3
import time
import logging
import re
from tqdm import tqdm

# -----------------------
# Logging setup
# -----------------------
logging.basicConfig(
    level=logging.DEBUG,  # Detailed logging for debugging
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -----------------------
# Configuration
# -----------------------
DB_PATH = "universal_image_archive.db"
TABLE_NAME = "archived_files"
TEXT_COLUMN = "description"  # Read from description column
OUTPUT_COLUMN = "xml_collection"  # Store category in xml_collection column
BATCH_SIZE = 100
MAX_RETRIES = 5
RETRY_DELAY = 0.5

# -----------------------
# Category rules
# -----------------------
category_rules = {
    'Actress': [r'actress', r'female (?:actor|star)\b', r'heroine'],
    'Actor': [r'actor', r'male (?:actor|star)\b', r'hero'],
    'Singer': [r'singer', r'vocalist', r'crooner'],
    'Musician': [r'musician', r'band', r'guitarist', r'drummer', r'pianist'],
    'Model': [r'model', r'fashion model', r'supermodel', r'pin[\s-]up'],
    'Politician': [r'politician', r'senator', r'governor', r'president', r'mayor'],
    'Athlete': [r'athlete', r'sports', r'player', r'olympian', r'runner'],
    'Artist': [r'artist', r'painter', r'sculptor', r'illustrator'],
    'Writer': [r'writer', r'author', r'novelist', r'poet'],
    'Director': [r'director', r'filmmaker', r'producer'],
    'Vintage': [r'vintage', r'retro', r'classic', r'19[0-5]\d'],
    'Modern': [r'modern', r'contemporary', r'20[0-2]\d'],
    'Portrait': [r'portrait', r'headshot', r'profile'],
    'Landscape': [r'landscape', r'scenery', r'nature', r'vista'],
    'Cityscape': [r'cityscape', r'urban', r'skyline'],
    'Historical': [r'historical', r'history', r'past', r'archive'],
    'Fashion': [r'fashion', r'clothing', r'style', r'couture'],
    'Film': [r'film', r'movie', r'cinema', r'motion picture'],
    'Music': [r'music', r'concert', r'performance', r'album'],
    'Sports': [r'sports', r'game', r'match', r'tournament'],
    'Art': [r'art', r'painting', r'drawing', r'sculpture'],
    'Photography': [r'photography', r'photo', r'snapshot', r'image'],
    'Travel': [r'travel', r'journey', r'destination', r'tourism'],
    'Nature': [r'nature', r'wildlife', r'forest', r'mountain', r'ocean'],
    'Architecture': [r'architecture', r'building', r'structure', r'monument'],
    'Event': [r'event', r'festival', r'celebration', r'ceremony'],
    'Technology': [r'technology', r'tech', r'gadget', r'device'],
    'Science': [r'science', r'experiment', r'research', r'lab'],
    'Food': [r'food', r'cuisine', r'dish', r'meal'],
    'Dance': [r'dance', r'ballet', r'choreography', r'dancer'],
    'Theater': [r'theater', r'play', r'drama', r'stage'],
    'Literature': [r'literature', r'book', r'novel', r'poetry'],
    'Fashion_Model': [r'fashion model', r'runway', r'catwalk'],
    'Celebrity': [r'celebrity', r'star', r'famous', r'icon'],
    'Historical_Figure': [r'historical figure', r'leader', r'king', r'queen'],
    'Street_Photography': [r'street photography', r'candid', r'urban life'],
    'Abstract': [r'abstract', r'modern art', r'non-figurative'],
    'Wildlife': [r'wildlife', r'animal', r'creature', r'fauna'],
    'Portrait_Photography': [r'portrait photography', r'studio portrait'],
    'Aerial': [r'aerial', r'drone', r"bird's eye", r'sky view'],
    'Documentary': [r'documentary', r'reportage', r'real-life'],
    'Black_White': [r'black and white', r'monochrome', r'grayscale'],
    'Color_Photography': [r'color photography', r'vivid', r'colorful'],
    'Vintage_Fashion': [r'vintage fashion', r'retro style', r'classic attire'],
    'Pop_Culture': [r'pop culture', r'trend', r'meme', r'popular'],
    'Fantasy': [r'fantasy', r'mythical', r'magic', r'surreal'],
    'SciFi': [r'sci-fi', r'science fiction', r'futuristic', r'space'],
    'War': [r'war', r'battle', r'military', r'conflict'],
    'Peace': [r'peace', r'harmony', r'tranquility', r'calm'],
    'Uncategorized': []
}

# -----------------------
# Database setup
# -----------------------
def setup_database(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def ensure_columns(conn):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({TABLE_NAME});")
    columns = [col[1] for col in cursor.fetchall()]
    logging.debug(f"Table columns: {columns}")
    
    # Check if description column exists
    if TEXT_COLUMN not in columns:
        logging.error(f"Column '{TEXT_COLUMN}' not found in table '{TABLE_NAME}'. Available columns: {columns}")
        conn.close()
        raise ValueError(f"Column '{TEXT_COLUMN}' does not exist in the database.")
    
    # Check if xml_collection column exists, create if missing
    if OUTPUT_COLUMN not in columns:
        logging.info(f"Adding '{OUTPUT_COLUMN}' column to the table.")
        cursor.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {OUTPUT_COLUMN} TEXT;")
        conn.commit()

# -----------------------
# Categorize text
# -----------------------
def categorize_text(text):
    if not text or not isinstance(text, str):
        logging.debug(f"Empty or invalid text: {text}, returning Uncategorized")
        return "Uncategorized"
    
    text = text.lower()  # Convert to lowercase for consistent matching
    logging.debug(f"Processing text: {text[:100]}...")
    for category, patterns in category_rules.items():
        for pattern in patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    logging.debug(f"Matched category '{category}' for pattern '{pattern}'")
                    return category
            except re.error as e:
                logging.error(f"Invalid regex pattern '{pattern}': {e}")
                continue
    logging.debug(f"No matches found for text, defaulting to Uncategorized")
    return "Uncategorized"

# -----------------------
# Batch update
# -----------------------
def insert_batch(conn, batch):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with conn:
                conn.executemany(
                    f"UPDATE {TABLE_NAME} SET {OUTPUT_COLUMN}=? WHERE id=?",
                    batch
                )
            return True
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                logging.warning(f"Database locked, retry {attempt}/{MAX_RETRIES}")
                time.sleep(RETRY_DELAY)
            else:
                raise
    return False

# -----------------------
# Fetch rows in batches
# -----------------------
def fetch_rows_in_batches(conn, batch_size=500):
    cursor = conn.cursor()
    cursor.execute(f"SELECT id, {TEXT_COLUMN} FROM {TABLE_NAME}")
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows

# -----------------------
# Main processing
# -----------------------
def process_rows(db_path):
    conn = setup_database(db_path)
    ensure_columns(conn)

    total_rows = 0
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    total_count = cursor.fetchone()[0]
    logging.info(f"Total rows to process: {total_count}")

    pbar = tqdm(total=total_count, unit="rows")
    for rows in fetch_rows_in_batches(conn, batch_size=BATCH_SIZE):
        batch = []
        for row in rows:
            row_id = row["id"]
            text = row[TEXT_COLUMN]
            category = categorize_text(text)
            batch.append((category, row_id))
        if not insert_batch(conn, batch):
            logging.error(f"Error processing batch at offset {total_rows}")
        total_rows += len(batch)
        pbar.update(len(batch))
    pbar.close()
    conn.close()
    logging.info("Processing complete.")

# -----------------------
# Peek first few rows
# -----------------------
def peek_database(db_path, num_rows=20):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT id, {TEXT_COLUMN}, {OUTPUT_COLUMN} FROM {TABLE_NAME} LIMIT {num_rows}")
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]
    for row in rows:
        row_dict = dict(zip(col_names, row))
        logging.info(f"Row: {row_dict}")
    conn.close()

# -----------------------
# Run script
# -----------------------
if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    process_rows(db_path)
    peek_database(db_path)