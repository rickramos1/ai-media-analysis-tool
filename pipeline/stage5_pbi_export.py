"""Stage 5 PBI export. Joins Stage 4b verdicts with article publish dates
and outlet ideology tags to produce the two CSVs the Power BI dashboard
consumes:

- data/misinfo_carriers_pbi.csv      (carrying verdicts only — the carrier list)
- data/stage4b_all_verdicts_pbi.csv  (full verdict set — used for rate measures)

Run after Stage 4b. Reads:
- data/stage4b_verdicts.json
- data/articles_classified.csv  (publish_date)
- IDEOLOGY_MAP from source_ideology_tagger.py
"""
import csv
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from source_ideology_tagger import IDEOLOGY_MAP, normalize_domain

VERDICTS_JSON = "data/stage4b_verdicts.json"
ARTICLES_CSV = "data/articles_classified.csv"
CARRIERS_PBI = "data/misinfo_carriers_pbi.csv"
ALL_VERDICTS_PBI = "data/stage4b_all_verdicts_pbi.csv"

csv.field_size_limit(2**30)


def article_domain_from_url(url):
    """Extract registrable domain from an article URL: strip www., lower-case."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def main():
    with open(VERDICTS_JSON) as f:
        verdicts = json.load(f)
    print(f"[input] {len(verdicts)} verdicts from {VERDICTS_JSON}")

    arts = pd.read_csv(ARTICLES_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    publish_dates = {r["url"]: r.get("publish_date", "") for _, r in arts.iterrows()}
    print(f"[input] {len(publish_dates)} article publish dates from {ARTICLES_CSV}")

    # Build enriched rows
    enriched = []
    missing_publish = 0
    for v in verdicts:
        article_url = v.get("article_url", "")
        article_outlet = v.get("article_outlet", "")
        fact_check_outlet = v.get("fact_check_outlet", "")

        article_domain = article_domain_from_url(article_url)
        article_ideology = IDEOLOGY_MAP.get(article_domain, "Unknown")
        # fact-check outlets in the verdicts file are already domain-style strings
        # (e.g. "factcheck.org"). Normalize the same way the article side does.
        fc_domain = normalize_domain(fact_check_outlet) or fact_check_outlet
        fc_ideology = IDEOLOGY_MAP.get(fc_domain, "Unknown")

        publish_date = publish_dates.get(article_url, "")
        if not publish_date:
            missing_publish += 1

        enriched.append({
            "article_url": article_url,
            "article_title": v.get("article_title", ""),
            "article_outlet": article_outlet,
            "article_outlet_domain": article_domain,
            "article_outlet_ideology": article_ideology,
            "article_topic": v.get("article_topic", ""),
            "article_publish_date": publish_date,
            "claim_id": v.get("claim_id", ""),
            "claim_text": v.get("claim_text", ""),
            "claim_source": v.get("claim_source", ""),
            "fact_check_outlet": fact_check_outlet,
            "fact_check_outlet_ideology": fc_ideology,
            "fact_check_url": v.get("fact_check_url", ""),
            "similarity": v.get("similarity", ""),
            "verdict": v.get("verdict", ""),
            "evidence_quote": v.get("evidence_quote") or "",
            "reasoning": v.get("reasoning", ""),
        })

    if missing_publish:
        print(f"[warn] {missing_publish} verdicts missing publish_date (article URL not in articles_classified.csv)")

    # Carriers-only PBI: filter + reorder columns
    carrier_fields = [
        "article_url", "article_title", "article_outlet", "article_outlet_domain",
        "article_outlet_ideology", "article_topic", "article_publish_date",
        "claim_text", "claim_source", "fact_check_outlet", "fact_check_outlet_ideology",
        "fact_check_url", "evidence_quote", "reasoning", "similarity", "verdict",
    ]
    carriers = [r for r in enriched if r["verdict"] == "carrying"]
    with open(CARRIERS_PBI, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=carrier_fields, quoting=csv.QUOTE_ALL,
                            extrasaction="ignore")
        w.writeheader()
        w.writerows(carriers)
    print(f"[write] {CARRIERS_PBI}: {len(carriers)} carrying verdicts "
          f"({len(set(r['article_url'] for r in carriers))} unique articles)")

    # All verdicts PBI: keeps claim_id, drops fact_check_outlet_ideology + fact_check_url
    all_fields = [
        "article_url", "article_title", "article_outlet", "article_outlet_domain",
        "article_outlet_ideology", "article_topic", "article_publish_date",
        "claim_id", "claim_text", "claim_source", "fact_check_outlet",
        "similarity", "verdict", "evidence_quote", "reasoning",
    ]
    with open(ALL_VERDICTS_PBI, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=all_fields, quoting=csv.QUOTE_ALL,
                            extrasaction="ignore")
        w.writeheader()
        w.writerows(enriched)
    print(f"[write] {ALL_VERDICTS_PBI}: {len(enriched)} verdicts")


if __name__ == "__main__":
    main()
