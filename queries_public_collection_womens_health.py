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
        "women’s health access": '\"women\'s health\" AND access'
    }

    topic_arg = sys.argv[1] if len(sys.argv) > 1 else None

    start_date = date(2022, 6, 24)
    end_date = date.today()

    all_articles = []

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
                break
            except Exception as e:
                if attempt < retries - 1:
                    print(f"Retry {attempt + 1}/{retries} after error: {e}")
                    time.sleep(10 * (attempt + 1))
                else:
                    print(f"❌ Error after {retries} retries: {e}")
                    stories = []

        for story in stories:
            story_id = story.get("story_id")
            full_text = ""
            if story_id:
                try:
                    detailed_story = search_api.story(story_id)
                    full_text = detailed_story.get("story_text", "")
                    print(f"[DEBUG] story_id={story_id}, story_text_len={len(full_text)}")
                except Exception as e:
                    print(f"⚠️ Failed to fetch full text for story ID {story_id}: {e}")

            all_articles.append({
                "topic": topic_name,
                "title": story.get("title", ""),
                "url": story.get("url", ""),
                "publish_date": story.get("publish_date", ""),
                "media_name": story.get("media_name", ""),
                "snippet": story.get("summary", ""),
                "full_text": full_text
            })

        time.sleep(2)

    print(f"\nSaved {len(all_articles)} total articles.")

    with open("womens_health_articles.csv", "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["topic", "title", "url", "publish_date", "media_name", "snippet", "full_text"])
        writer.writeheader()
        writer.writerows(all_articles)

if __name__ == "__main__":
    run_womens_health_queries()