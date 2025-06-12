import csv
import time
import argparse
from newspaper import Article
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_THREADS = 5


def scrape_article_text(row):
    url = row.get("url", "")
    try:
        article = Article(url)
        article.download()
        article.parse()
        text = article.text.strip()
    except Exception as e:
        text = f"ERROR: {str(e)}"

    row["full_text"] = text
    return row, url, len(text.split())


def scrape_all(input_file, output_file):
    with open(input_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

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
            print(f"[{i}/{len(rows_to_scrape)}] Scraped {url[:60]}... → {word_count} words")

    with open(output_file, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=enriched_rows[0].keys())
        writer.writeheader()
        writer.writerows(enriched_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--infile", required=True, help="Path to CSV with article URLs")
    parser.add_argument("--outfile", required=True, help="Path to save enriched CSV")
    args = parser.parse_args()

    scrape_all(args.infile, args.outfile)
