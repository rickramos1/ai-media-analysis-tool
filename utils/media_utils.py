# utils/media_utils.py
from config import directory_api

def find_sources_by_name(keyword, limit=10):
    sources = directory_api.source_list(name=keyword, rows=limit)
    return [(s['media_id'], s['name']) for s in sources]
