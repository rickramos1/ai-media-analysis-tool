import time
import requests
import pandas as pd
import re
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_THREADS = 5
DEFAULT_INPUT_FILE = "womens_health_articles.csv"
DEFAULT_OUTPUT_FILE = "womens_health_articles_text.csv"

def clean_text(text):
    text = text.replace('"', '""')  # double quotes for CSV compatibility
    text = text.replace("\\", "\\\\")  # escape backslashes
    text = re.sub(r"[\x00-\x1F\x7F]", " ", text)  # remove control chars
    text = re.sub(r"\s+", " ", text).strip()  # collapse whitespace
    return text

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def scrape_article_text(row):
    url = row.get("url", "")
    if not url or not url.startswith("http"):
        row["full_text"] = ""
        return row, url, 0
    try:
        response = requests.get(url, timeout=15, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        text = "\n".join(p.get_text() for p in paragraphs if p.get_text().strip())
        text = clean_text(text)
    except Exception as e:
        text = f"ERROR: {str(e)}"
    row["full_text"] = text
    return row, url, len(text.split())

def scrape_all(input_file, output_file):
    df = pd.read_csv(input_file, dtype=str, keep_default_na=False)
    rows = df.to_dict(orient="records")

    enriched_rows = []
    rows_to_scrape = []

    for row in rows:
        if row.get("full_text") and len(row["full_text"].strip()) > 30:
            enriched_rows.append(row)
        else:
            rows_to_scrape.append(row)

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_row = {executor.submit(scrape_article_text, row): row for row in rows_to_scrape}

        for i, future in enumerate(as_completed(future_to_row), 1):
            row, url, word_count = future.result()
            enriched_rows.append(row)
            print(f"[{i}/{len(rows_to_scrape)}] Scraped {url[:60]}... -> {word_count} words")

    pd.DataFrame(enriched_rows).to_csv(output_file, index=False, quoting=1)  # quoting=1 = QUOTE_ALL

if __name__ == "__main__":
    scrape_all(DEFAULT_INPUT_FILE, DEFAULT_OUTPUT_FILE)
