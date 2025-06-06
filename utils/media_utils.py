# utils/media_utils.py
from config import directory_api
from datetime import date, timedelta
from config import search_api

def find_sources_by_name(keyword, limit=10):
    sources = directory_api.source_list(name=keyword, rows=limit)
    return [(s['media_id'], s['name']) for s in sources]

def has_recent_stories(source_id, days=90):
    today = date.today()
    start_date = today - timedelta(days=days)
    results, _ = search_api.story_list(
        query="*", source_ids=[source_id],
        start_date=start_date, end_date=today, page_size=1
    )
    return len(results) > 0
