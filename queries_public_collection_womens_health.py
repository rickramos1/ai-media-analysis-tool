# queries_public_collection_womens_health.py

from datetime import date, datetime
from config import search_api
import csv
import sys
import time

def run_womens_health_queries():
    TOPIC_QUERIES = {
        "abortion misinformation": '"abortion" AND (myth OR hoax OR false OR fake OR "not safe" OR "causes cancer" OR "causes infertility" OR "abortion is murder" OR "abortion reversal")',
        "birth control myths": '"birth control" AND (myth OR misinformation OR "causes infertility" OR "does not work" OR "dangerous" OR "natural method only")',
        "emergency contraception": '("plan b" OR "emergency contraception") AND ("causes abortion" OR myth OR misinformation OR "not effective")',
        "mifepristone misinformation": '("mifepristone" OR "abortion pill") AND (dangerous OR fake OR hoax OR myth OR reversal OR infertility)',
        "pregnancy crisis centers": '("pregnancy crisis center" OR "pregnancy resource center") AND (misinformation OR deceptive OR misleading OR fake OR "anti-abortion")'
    }

    COLLECTION_IDS = [34412234]
    START_DATE = date(2022, 6, 24)  # Roe v. Wade overturned
    END_DATE = date.today()
    PAGE_SIZE = 100
    MAX_PAGES = 10  # Max pages per topic to avoid runaway queries

    topic_arg = sys.argv[1] if len(sys.argv) > 1 else None

    all_articles = []

    for topic_name, query_string in TOPIC_QUERIES.items():
        if topic_arg and topic_name != topic_arg:
            continue

        print(f"\n[{datetime.now()}] Running query for topic: {topic_name}")
        print(f"[QUERY] {query_string}")

        pagination_token = None
        topic_count = 0
        page = 0

        while page < MAX_PAGES:
            page += 1
            retries = 3
            stories = []

            for attempt in range(retries):
                try:
                    stories, pagination_token = search_api.story_list(
                        query=query_string,
                        collection_ids=COLLECTION_IDS,
                        start_date=START_DATE,
                        end_date=END_DATE,
                        page_size=PAGE_SIZE,
                        pagination_token=pagination_token,
                        sort_order='desc'
                    )
                    print(f"  Page {page}: retrieved {len(stories)} stories")
                    break
                except Exception as e:
                    if attempt < retries - 1:
                        print(f"  Retry {attempt + 1}/{retries} after error: {e}")
                        time.sleep(10 * (attempt + 1))
                    else:
                        print(f"  Failed after {retries} retries: {e}")
                        stories = []
                        pagination_token = None

            for story in stories:
                all_articles.append({
                    "topic": topic_name,
                    "title": story.get("title", ""),
                    "url": story.get("url", ""),
                    "publish_date": story.get("publish_date", ""),
                    "media_name": story.get("media_name", ""),
                    "media_url": story.get("media_url", ""),
                    "language": story.get("language", ""),
                    "story_id": story.get("id", ""),
                })
                topic_count += 1

            if not pagination_token:
                break
            time.sleep(1)

        print(f"  Total for {topic_name}: {topic_count} articles")

    print(f"\nTotal articles collected: {len(all_articles)}")

    output_file = "womens_health_articles.csv"
    fieldnames = ["topic", "title", "url", "publish_date", "media_name", "media_url", "language", "story_id"]
    with open(output_file, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_articles)

    print(f"Saved to {output_file}")

if __name__ == "__main__":
    run_womens_health_queries()
