# queries_public_collection_misc_topics.py

from datetime import date
from config import search_api
import csv

def run_misc_topic_queries():
    TOPIC_QUERIES = {
        "Panda bears": '"Panda bears"',
        "climate change": '"climate change"'
    }

    start_date = date(2022, 6, 24)
    end_date = date.today()

    results = []

    for topic_name, query_string in TOPIC_QUERIES.items():
        print(f"Running query for topic: {topic_name}")
        try:
            stories, _ = search_api.story_list(
                query=query_string,
                collection_ids=[34412234],  # Global Mainstream Media
                start_date=start_date,
                end_date=end_date,
                page_size=100
            )
            count = len(stories)
            status = "✅ OK" if count >= 1 else "❌ Too few"
        except Exception as e:
            count = 0
            status = f"❌ Error: {e}"

        results.append({
            "query": topic_name,
            "region": "global_mainstream",
            "story_count": count,
            "status": status
        })

    print(f"\n{'Query':<30} {'Region':<20} {'Stories':<10} {'Status'}")
    print("-" * 70)
    for row in results:
        print(f"{row['query']:<30} {row['region']:<20} {row['story_count']:<10} {row['status']}")

    with open("misc_topic_results.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "region", "story_count", "status"])
        writer.writeheader()
        writer.writerows(results)

if __name__ == "__main__":
    run_misc_topic_queries()
