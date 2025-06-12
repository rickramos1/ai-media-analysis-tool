# newsapi_timeseries.py

import requests
from datetime import datetime, timedelta
import csv
import os
from dotenv import load_dotenv

# Load API key
load_dotenv()
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# Parameters
QUERIES = {
    "abortion_misinformation": ["abortion", "infertility", "cancer"],
    "planb_sterilization": ["Plan B", "sterilization"],
    "roe_lies": ["Roe v Wade", "lies"],
    "abortion_pill_reversal": ["abortion pill", "reversal"],
    "general_misinformation": ["misinformation", "abortion"]
}

DOMAINS = {
    "us_left": "msnbc.com,cnn.com,huffpost.com",
    "us_right": "foxnews.com,breitbart.com,newsmax.com"
}

START_DATE = datetime(2022, 6, 24)
END_DATE = datetime.today()
MAX_PAGES = 5  # Each page returns up to 100 results

# NewsAPI Endpoint
NEWS_API_URL = "https://newsapi.org/v2/everything"

results = []

for query_name, keywords in QUERIES.items():
    for group_name, domains in DOMAINS.items():
        q = " AND ".join(keywords)
        print(f"🔍 {query_name} in {group_name}...")

        for day_offset in range((END_DATE - START_DATE).days + 1):
            day = START_DATE + timedelta(days=day_offset)
            from_param = day.strftime("%Y-%m-%d")
            to_param = (day + timedelta(days=1)).strftime("%Y-%m-%d")

            total_hits = 0

            for page in range(1, MAX_PAGES + 1):
                params = {
                    "q": q,
                    "from": from_param,
                    "to": to_param,
                    "domains": domains,
                    "apiKey": NEWS_API_KEY,
                    "pageSize": 100,
                    "page": page,
                    "language": "en",
                    "sortBy": "relevancy"
                }

                response = requests.get(NEWS_API_URL, params=params)
                if response.status_code != 200:
                    print(f"❌ Error {response.status_code}: {response.text}")
                    break

                data = response.json()
                total_hits += len(data.get("articles", []))

                if len(data.get("articles", [])) < 100:
                    break  # No more pages

            results.append({
                "date": from_param,
                "query": query_name,
                "media_group": group_name,
                "count": total_hits
            })

# Save to CSV
with open("newsapi_timeseries_output.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["date", "query", "media_group", "count"])
    writer.writeheader()
    writer.writerows(results)

print(f"✅ Done! {len(results)} rows written to newsapi_timeseries_output.csv")
