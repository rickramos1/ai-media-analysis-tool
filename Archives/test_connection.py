from mediacloud.api import SearchApi, DirectoryApi
from datetime import date

# Replace with your actual API key or import from config
API_KEY = os.getenv("MEDIACLOUD_API_KEY")
mc = SearchApi(API_KEY)

try:
    # Basic query to check connection
    stories, _ = mc.story_list(
        query="AI",
        start_date=date(2024, 12, 1),
        end_date=date(2025, 6, 1),
        collection_ids=[1],  # US Top Sources (public)
        page_size=1
    )

    print(f"✅ Connected. Returned {len(stories)} stories.")
    if stories:
        print(f"Sample story: {stories[0]['title']} — {stories[0]['media_name']}")

except Exception as e:
    print(f"❌ Connection failed: {e}")
