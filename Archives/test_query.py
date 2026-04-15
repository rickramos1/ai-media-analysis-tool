from mediacloud.api import SearchApi
from datetime import date

mc = SearchApi(os.getenv("MEDIACLOUD_API_KEY"))

results = mc.story_count(
    query="*",
    collection_ids=[1],
    start_date=date(2023, 1, 1),
    end_date=date(2023, 12, 31)
)

print(results)
