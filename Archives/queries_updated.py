# queries.py

from datetime import date, timedelta
from config import search_api
import csv

# ✅ Change these for different tests
TEST_QUERY_NAME = "U.S. economy"
TEST_QUERY = '"U.S. economy"'
TEST_REGION_NAME = "us_top"
TEST_COLLECTION_ID = 1  # U.S. Top Sources

def test_query_volume():
    two_years_ago = date.today() - timedelta(days=730)
    today = date.today()

    results = []

    try:
        stories, _ = search_api.story_list(
            query=TEST_QUERY,
            collection_ids=[TEST_COLLECTION_ID],
            start_date=two_years_ago,
            end_date=today,
            page_size=100
        )
        count = len(stories)
    except Exception as e:
        print(f"❌ Error fetching stories: {e}")
        count = 0

    status = "✅ OK" if count >= 1 else "❌ Too few"

    results.append({
        "query": TEST_QUERY_NAME,
        "region": TEST_REGION_NAME,
        "story_count": count,
        "status": status
    })

    return results

def run_womens_health_queries():
    TOPIC_QUERIES = {
        "abortion misinformation": '"abortion" AND ("misinformation" OR "disinformation")',
        "birth control myths": '"birth control" AND ("myth" OR "misinformation")',
        "abortion and infertility": '"abortion causes infertility"',
        "abortion pill misinformation": '"abortion pill" AND ("dangerous" OR "unsafe" OR "myth")',
        "women’s health post-Roe": '("women\'s health" OR "reproductive health") AND "Roe v. Wade"'
    }

    dobbs_date = date(2022, 6, 24)
    today = date.today()

    womens_health_results = []

    for topic_name, query_string in TOPIC_QUERIES.items():
        try:
            stories, _ = search_api.story_list(
                query=query_string,
                collection_ids=[1],
                start_date=dobbs_date,
                end_date=today,
                page_size=100
            )
            count = len(stories)
            status = "✅ OK" if count >= 1 else "❌ Too few"
        except Exception as e:
            count = 0
            status = f"❌ Error: {e}"

        womens_health_results.append({
            "query": topic_name,
            "region": "us_top",
            "story_count": count,
            "status": status
        })

    print(f"\n{'Query':<30} {'Region':<20} {'Stories':<10} {'Status'}")
    print("-" * 70)
    for row in womens_health_results:
        print(f"{row['query']:<30} {row['region']:<20} {row['story_count']:<10} {row['status']}")

    with open("womens_health_misinfo_results.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "region", "story_count", "status"])
        writer.writeheader()
        writer.writerows(womens_health_results)

if __name__ == "__main__":
    data = test_query_volume()

    print(f"{'Query':<30} {'Region':<20} {'Stories':<10} {'Status'}")
    print("-" * 70)
    for row in data:
        print(f"{row['query']:<30} {row['region']:<20} {row['story_count']:<10} {row['status']}")

    with open("query_results.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "region", "story_count", "status"])
        writer.writeheader()
        writer.writerows(data)

    run_womens_health_queries()
