from mediacloud.api import MediaCloud
from dotenv import load_dotenv
import os
import csv
from datetime import date, timedelta

load_dotenv()
API_KEY = os.getenv("MEDIACLOUD_API_KEY")

mc = MediaCloud(API_KEY)

QUERIES = {
    "abortion_misinformation": '"abortion AND (infertility OR cancer)"',
    "planb_sterilization": '"Plan B AND sterilization"',
    "roe_lies": '"Roe v Wade AND lies"',
    "abortion_pill_reversal": '"abortion pill AND reversal"',
    "general_misinformation": '"misinformation AND abortion"'
}

MEDIA_GROUPS = {
    "us_left": [1, 4, 6, 17, 17592],
    "us_right": [12, 9219, 17591, 9224, 9241],
    "eu_general": [22348, 23952, 27513, 23537, 24094],
    "asia_general": [23394, 23387, 23528, 23803, 23804]
}

DAYS_BACK = 180  # how far back to pull timeseries

# --- INITIALIZE API ---
mc = mediacloud.api.MediaCloud(API_KEY)

# --- COLLECT TIMESERIES DATA ---
end_date = date.today()
start_date = end_date - timedelta(days=DAYS_BACK)
results = []

for query_name, query_str in QUERIES.items():
    for group_name, media_ids in MEDIA_GROUPS.items():
        print(f"Running: {query_name} in {group_name}")
        try:
            ts = mc.storyCount(query_str, solr_filter=[f'media_id:{",".join(map(str, media_ids))}'],
                               split=True, split_period='day',
                               start_date=start_date.isoformat(),
                               end_date=end_date.isoformat())
            for point in ts['counts']:
                results.append({
                    "date": point['date'],
                    "query": query_name,
                    "media_group": group_name,
                    "count": point['count']
                })
        except Exception as e:
            print(f"Error for {query_name} / {group_name}: {e}")

# --- WRITE TO CSV ---
with open("timeseries_output.csv", "w", newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=["date", "query", "media_group", "count"])
    writer.writeheader()
    writer.writerows(results)

print("✅ Done! Output written to timeseries_output.csv")
