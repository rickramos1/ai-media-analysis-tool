# queries_public_collection_womens_health.py

from datetime import date, datetime
from config import search_api
import csv
import sys
import time

def run_womens_health_queries():
    TOPIC_QUERIES = {
        "abortion misinformation": '"abortion" AND ("misinformation" OR "disinformation")',
        "birth control myths": '"birth control" AND ("myth" OR "misinformation")',
        "contraceptive misinformation": '"contraceptive" AND misinformation',
        "reproductive health funding": '"reproductive health" AND (funding OR policy)',
        "women’s health access": '"women\'s health" AND access'
    }

    topic_arg = sys.argv[1] if len(sys.argv) > 1 else None

    start_date = date(2022, 6, 24)
    end_date = date.today()

    results = []

    for topic_name, query_string in TOPIC_QUERIES.items():
        if topic_arg and topic_name != topic_arg:
            continue

        print(f"[{datetime.now()}] Running query for topic: {topic_name}")

        retries = 3
        for attempt in range(retries):
            try:
                stories, _ = search_api.story_list(
                    query=query_string,
                    collection_ids=[34412234],
                    start_date=start_date,
                    end_date=end_date,
                    page_size=100
                )
                count = len(stories)
                status = "✅ OK" if count >= 1 else "❌ Too few"
                break
            except Exception as e:
                if attempt < retries - 1:
                    print(f"Retry {attempt + 1}/{retries} after error: {e}")
                    time.sleep(10 * (attempt + 1))
                else:
                    count = 0
                    status = f"❌ Error after {retries} retries: {e}"

        results.append({
            "query": topic_name,
            "region": "global_mainstream",
            "story_count": count,
            "status": status
        })

        time.sleep(2)

    print(f"\n{'Query':<30} {'Region':<20} {'Stories':<10} {'Status'}")
    print("-" * 70)
    for row in results:
        print(f"{row['query']:<30} {row['region']:<20} {row['story_count']:<10} {row['status']}")

    with open("womens_health_misinfo_results.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "region", "story_count", "status"])
        writer.writeheader()
        writer.writerows(results)

if __name__ == "__main__":
    run_womens_health_queries()
