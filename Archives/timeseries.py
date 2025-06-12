# gdelt_timeseries.py

import csv
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import requests
import gzip
import io

# ----------------------------
# ✅ Define your queries here
# ----------------------------
QUERIES = {
    "abortion_misinformation": ["abortion", "infertility", "cancer"],
    "planb_sterilization": ["Plan B", "sterilization"],
    "roe_lies": ["Roe v Wade", "lies"],
    "abortion_pill_reversal": ["abortion pill", "reversal"],
    "general_misinformation": ["misinformation", "abortion"]
}

DAYS_BACK = 7  # for testing, limit to last 7 days
BASE_URL = "http://data.gdeltproject.org/gdeltv2/"

# ----------------------------
# 🧠 Pull and analyze daily GKG files
# ----------------------------
def fetch_and_aggregate():
    end_date = datetime.now(timezone.utc) - timedelta(hours=48)
    start_date = end_date - timedelta(days=DAYS_BACK)

    results = []
    current = start_date

    while current <= end_date:
        hour = current.strftime("%Y%m%d%H00")
        url = f"{BASE_URL}gkg/{hour}.gkg.csv.zip"
        print(f"⏳ Downloading: {url}")

        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"⚠️ Skipped {hour}: {resp.status_code}")
                current += timedelta(hours=1)
                continue

            with gzip.open(io.BytesIO(resp.content), 'rt', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f, delimiter='\t')

                query_hits = defaultdict(int)
                for row in reader:
                    if len(row) < 4:
                        continue
                    doc_date = row[1][:8]
                    themes_text = row[9] if len(row) > 9 else ""
                    for qname, keywords in QUERIES.items():
                        if any(kw.lower() in themes_text.lower() for kw in keywords):
                            query_hits[(qname, doc_date)] += 1

                for (qname, doc_date), count in query_hits.items():
                    results.append({
                        "date": doc_date,
                        "query": qname,
                        "count": count
                    })

        except Exception as e:
            print(f"❌ Error for {hour}: {e}")

        current += timedelta(hours=1)

    return results

# ----------------------------
# 📄 Write CSV
# ----------------------------
if __name__ == "__main__":
    data = fetch_and_aggregate()

    with open("gdelt_timeseries_output.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "query", "count"])
        writer.writeheader()
        writer.writerows(data)

    print(f"✅ Done! {len(data)} rows written to gdelt_timeseries_output.csv")
