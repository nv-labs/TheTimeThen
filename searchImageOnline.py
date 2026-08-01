# searchImageBingCommercial.py – Updated Dec 2025: Better Selectors & Waits for Bing Images
import sqlite3, os, requests, time, re, argparse, base64
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    StaleElementReferenceException, NoSuchElementException,
    TimeoutException, ElementClickInterceptedException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
import io
from selenium.webdriver.common.keys import Keys

DB_NAME = 'universal_image_archive.db'
TABLE = 'photos_searched'

# --- Database & Utility Functions (unchanged) ---

def create_table():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(f'''
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_size INTEGER,
            file_data BLOB NOT NULL,
            source_url TEXT NOT NULL,
            file_type TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            xml_collection TEXT,
            xml_date TEXT,
            xml_subject TEXT,
            xml_language TEXT,
            xml_title TEXT UNIQUE,
            description TEXT,
            VideoAirDate TEXT
        )
    ''')
    conn.commit()
    return conn

def title_unique(cur, base):
    if not base or not isinstance(base, str):
        base = "Untitled"
    base = re.sub(r'[^\w\s\-\.\,]', '', base)[:140].strip()
    if not base:
        base = "Untitled"
    orig, i = base, 1
    while True:
        cur.execute(f"SELECT 1 FROM {TABLE} WHERE xml_title=?", (base,))
        if not cur.fetchone():
            return base
        base = f"{orig}_{i}"
        i += 1

def already_exists(cur, url):
    cur.execute(f"SELECT 1 FROM {TABLE} WHERE source_url=?", (url,))
    return cur.fetchone()

def valid_image(data):
    try:
        Image.open(io.BytesIO(data)).verify()
        return True
    except Exception:
        return False

def insert(conn, fn, data, url, ext, title, desc):
    title = str(title) if title else "Untitled"
    desc = str(desc) if desc else "No description available."
    cur = conn.cursor()
    cur.execute(f'''
        INSERT INTO {TABLE}
        (filename, file_size, file_data, source_url, file_type, added_date,
         xml_collection, xml_date, xml_subject, xml_language, xml_title,
         description, VideoAirDate)
        VALUES (?,?,?,?,?,datetime('now'),?,?,?,?,?,?,?)
    ''', (fn, len(data), data, url, ext, '', '', '', '', title, desc, ''))
    conn.commit()
    print(f"Inserted: {fn} → {title}")
    print(f"           Description: {desc}")

# --- Metadata Function ---

def get_real_metadata(driver):
    title = "Untitled"
    desc = "No description available."
    try:
        title = driver.title.strip().split(" - Bing")[0].strip()
        if not title:
            try:
                title = driver.find_element(By.TAG_NAME, "h1").text.strip()
            except NoSuchElementException:
                pass
        try:
            alt = driver.find_element(By.XPATH, '//img[contains(@src,"th.bing.com") and (contains(@class,"main") or contains(@class,"rich") or @id="mainImage")]').get_attribute("alt")
            if alt and alt.lower() not in ["image", ""]:
                desc = alt.strip()
        except NoSuchElementException:
            pass
        title = re.sub(r'\s+', ' ', title)[:140].strip()
        desc = re.sub(r'\s+', ' ', desc)[:300].strip()
        if desc and not desc.endswith(('.', '!', '?')):
            desc += "."
    except Exception as e:
        print(f"Metadata failed: {e}")
    return title, desc

# --- Scrape Function ---

def scrape(query: str, limit: int = 10):
    conn = create_table()
    cur = conn.cursor()

    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--remote-debugging-port=9222")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    print(f"Searching Bing Images: \"{query}\" (Free to modify, share, and use commercially)")

    encoded_query = query.replace(' ', '+')
    url = f"https://www.bing.com/images/search?q={encoded_query}&license=ModifyCommercially"
    driver.get(url)
    time.sleep(8)

    # Accept cookies
    try:
        accept = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "bnp_btn_accept")))
        accept.click()
        time.sleep(2)
    except Exception:
        pass

    print("Scrolling to load more results...")
    for _ in range(8):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

    # Updated thumbnail XPath – more robust for current Bing (includes rms_img if present)
    thumbs_xpath = '//img[@class="mimg" or contains(@class,"rms_img") or contains(@class,"mimg")]'

    thumbs = driver.find_elements(By.XPATH, thumbs_xpath)
    if not thumbs:
        print("No images found – selectors may have changed.")
        driver.quit()
        conn.close()
        return

    print(f"Found {len(thumbs)} potential thumbnails → attempting to get {limit} images")

    added = 0
    i = 0

    while added < limit and i < len(thumbs):
        try:
            # Close any open preview pane
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1.5)

            # Re-fetch thumbnails
            thumbs = driver.find_elements(By.XPATH, thumbs_xpath)
            if i >= len(thumbs):
                break

            thumb = thumbs[i]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", thumb)
            time.sleep(1)

            driver.execute_script("arguments[0].click();", thumb)
            time.sleep(3)  # Longer wait for preview to fully load

            # Broader wait for any large image with real Bing src
            full_img = WebDriverWait(driver, 25).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//img[contains(@src,"th.bing.com") and (contains(@src,"&amp;w=") or contains(@src,"?w=")) and not(contains(@src,"&amp;w=150"))]')
                )
            )

            img_url = full_img.get_attribute("src")
            if not img_url:
                img_url = full_img.get_attribute("data-src")

            if not img_url or not img_url.startswith("http") or already_exists(cur, img_url):
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                i += 1
                continue

            # Download & validate
            r = requests.get(img_url, timeout=20)
            if r.status_code != 200 or len(r.content) < 8000 or not valid_image(r.content):
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                i += 1
                continue
            data = r.content

            # Metadata
            real_title, real_desc = get_real_metadata(driver)

            # Save
            title = title_unique(cur, real_title)
            fn = f"{query.replace(' ', '_')}_{added+1}.jpg"
            insert(conn, fn, data, img_url, "jpg", title, real_desc)
            added += 1

            # Close preview
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(2)
            i += 1

        except TimeoutException:
            print(f"Timeout waiting for full image on index {i} – trying next")
            try:
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except:
                pass
            i += 1
        except Exception as e:
            print(f"Error on index {i}: {e}")
            i += 1

    driver.quit()
    conn.close()
    print(f"\nDone! Saved {added} commercially usable images.")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Scrapes Bing Images with commercial-use license.")
    p.add_argument("query", help="Search query")
    p.add_argument("--limit", type=int, default=10, help="Max images (default: 10)")
    args = p.parse_args()
    scrape(args.query, args.limit)