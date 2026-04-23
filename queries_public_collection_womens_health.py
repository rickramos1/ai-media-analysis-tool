# queries_public_collection_womens_health.py

from datetime import date, datetime
from config import search_api
import csv
import sys
import time

# Carrier-focused queries: use the promotional/advocacy language that misinfo
# carriers use, not the meta-vocabulary fact-checkers use (myth, hoax,
# misinformation). NOT-clauses help exclude debunkers of the same terms.
# See BACKLOG.md "Cross-reference misinfo detection" for context.
TOPIC_QUERIES = {
    "abortion pill reversal": (
        '("abortion pill reversal" OR "APR protocol" OR "mifepristone reversal") '
        'AND NOT ("no evidence" OR "debunked" OR "not FDA-approved" OR "pseudoscience")'
    ),
    "chemical abortion harms": (
        '"chemical abortion" AND ("hurts women" OR "endangers women" OR '
        'complications OR "hemorrhage" OR "emergency room" OR "unsafe")'
    ),
    "emergency contraception abortifacient": (
        '("Plan B" OR "emergency contraception" OR "morning-after pill" OR "ella") AND '
        '(abortifacient OR "ends a pregnancy" OR "causes abortion" OR "prevents implantation")'
    ),
    "birth control harm claims": (
        '("birth control" OR "the pill" OR "hormonal contraception") AND '
        '("causes cancer" OR "causes depression" OR "causes infertility" OR '
        '"ruined my" OR "hormone imbalance" OR "dangers of" OR "got off" OR "quit")'
    ),
    "IUD misinfo": (
        '(IUD OR "intrauterine") AND '
        '(abortifacient OR "causes abortion" OR "perforates" OR "trauma" OR "ruined")'
    ),
    "mifepristone safety attack": (
        '(mifepristone OR "abortion pill") AND '
        '("FDA rushed" OR "not safe" OR "adverse events" OR "REMS failed" OR '
        '"Biden deregulated" OR "contaminates water" OR "environmental threat")'
    ),
    "fertility awareness superiority": (
        '("fertility awareness" OR "natural family planning" OR "NFP" OR "cycle tracking") AND '
        '(effective OR "just as" OR "more effective" OR alternative OR "no side effects")'
    ),
    "CPC promotion": (
        '("pregnancy resource center" OR "pregnancy help center" OR "crisis pregnancy center") AND '
        '("free ultrasound" OR ministry OR "abortion alternatives" OR "pro-life" OR "baby boxes") '
        'AND NOT ("deceptive" OR "misleading" OR "investigation")'
    ),
    "trad wife anti-contraception": (
        '("trad wife" OR "traditional wife" OR "homeschool mom") AND '
        '("birth control" OR contraception OR "natural cycle" OR fertility)'
    ),
    "wellness hormone influencers": (
        '("hormonal imbalance" OR "fix your hormones" OR "balance hormones" OR '
        '"seed cycling") AND (natural OR detox OR "root cause" OR supplement)'
    ),
}


def run_womens_health_queries():
    COLLECTION_IDS = [34412234]
    START_DATE = date(2022, 6, 24)  # Roe v. Wade overturned
    END_DATE = date.today()
    PAGE_SIZE = 100
    MAX_PAGES = 20  # raised from 10 — carrier queries are more specific so per-topic volume is lower

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
