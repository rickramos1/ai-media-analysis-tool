import random
import re
import time

import pandas as pd
import requests
import trafilatura
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_THREADS = 5
DEFAULT_INPUT_FILE = "womens_health_articles.csv"
DEFAULT_OUTPUT_FILE = "womens_health_articles_text.csv"

# Rotate through realistic human-browser User-Agents, including DuckDuckGo
# Privacy Browser on macOS/iOS/Android. Helps get past static bot-filter
# heuristics. Does NOT defeat TLS fingerprinting or JS challenges — if WAF
# errors persist, the next tier is curl_cffi or playwright.
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 DuckDuckGo/7 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1 Ddg/7",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36 DuckDuckGo/5",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

REFERERS = [
    "https://duckduckgo.com/",
    "https://www.google.com/",
    "https://news.google.com/",
    "",  # some requests without referer — also human behavior
]


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"[\x00-\x1F\x7F]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def browser_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Referer": random.choice(REFERERS),
    }


def scrape_article_text(row):
    url = row.get("url", "")
    if not url or not url.startswith("http"):
        row["full_text"] = ""
        return row, url, 0
    try:
        time.sleep(random.uniform(0.3, 1.5))
        response = requests.get(url, timeout=15, headers=browser_headers())
        response.raise_for_status()
        extracted = trafilatura.extract(
            response.text,
            url=url,
            favor_precision=True,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        text = clean_text(extracted or "")
    except Exception as e:
        print(f"[scrape] {url} -> {e}", flush=True)
        text = ""
    row["full_text"] = text
    return row, url, len(text.split())

def scrape_all(input_file, output_file):
    df = pd.read_csv(input_file, dtype=str, keep_default_na=False)
    rows = df.to_dict(orient="records")

    enriched_rows = []
    rows_to_scrape = []

    for row in rows:
        existing = (row.get("full_text") or "").strip()
        if existing and len(existing) > 30 and not existing.startswith("ERROR:"):
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
