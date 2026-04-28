"""Fetch fact-checks from outside the MediaCloud corpus to enlarge the
canonical-claim universe (BACKLOG #1).

Today the canonical claim database is bottlenecked at the FACT_CHECK articles
that MediaCloud happens to return. Anything debunked by AP/Reuters/Snopes/
PolitiFact but absent from those queries is invisible to Stage 4. This script
queries the Google Fact Check Tools API (which aggregates ClaimReview-marked
content from publishers worldwide), filters results to women's-health
debunked claims, and emits a JSON file in the same shape as `claims.json` so
Stage 3 can consume it alongside the in-corpus claims.

Usage:
    # one-shot: search for a single phrase
    python pipeline/external_factchecks.py --query "abortion pill reversal"

    # batch: run the default women's-health query set
    python pipeline/external_factchecks.py --default-queries

    # then re-run Stage 3 with the union as input:
    python pipeline/stage3_filter.py --extra-input data/external_factchecks_claims.json

Requires GOOGLE_FACTCHECK_API_KEY in .env
(get one at https://console.cloud.google.com/, enable "Fact Check Tools API").
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from claim_normalizer import WOMENS_HEALTH_RX  # noqa: E402

load_dotenv()

API_KEY = os.environ.get("GOOGLE_FACTCHECK_API_KEY")
API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
PAGE_SIZE = 50  # max per Google docs

INPUT_CORPUS_CLAIMS = "data/claims.json"  # for URL dedupe
OUTPUT_RAW = "data/external_factchecks_raw.json"
OUTPUT_CLAIMS = "data/external_factchecks_claims.json"

# Default search phrases — each becomes one API query. The Google Fact Check
# Tools API does AND-of-words matching on the claim text, so multi-word
# phrases drastically over-constrain. Single-word queries fan out far better.
# Empirically: "abortion pill reversal" returns 0 hits, "abortion pill"
# returns 20+. Down-stream women's-health filtering is handled by
# WOMENS_HEALTH_RX in the adapter.
DEFAULT_QUERIES = [
    "mifepristone",
    "abortion pill",
    "chemical abortion",
    "Plan B",
    "morning after pill",
    "emergency contraception",
    "IUD",
    "birth control",
    "contraception",
    "fertility awareness",
    "crisis pregnancy center",
    "Project 2025 abortion",
]

# Verdict ratings that count as "debunked" — i.e. the claim is being refuted.
# ClaimReview textualRating is free-text per publisher; some put a verdict
# label ("False"), others put a prose refutation ("The morning after pill
# doesn't induce an abortion..."). We try both: an allow-list for verdict
# labels, and a deny-list for clearly-affirmative ratings ("True", "Half
# True", etc.) that lets long prose ratings through as refutations.
DEBUNKED_RATING_RX = re.compile(
    r"\b(false|incorrect|wrong|misleading|misrepresent|unsupported|unproven|"
    r"inaccurate|baseless|fake|fabricat|debunk|no evidence|not (true|supported)|"
    r"pants on fire|four pinocchios|three pinocchios|mostly false|partly false)\b",
    re.IGNORECASE,
)
# Ratings that explicitly affirm the claim — never treat as debunked.
AFFIRMING_RATING_RX = re.compile(
    r"^\s*(true|mostly true|half true|partly true|correct|verified|confirmed|accurate)\s*$",
    re.IGNORECASE,
)


def domain_of(url_or_name: str) -> str:
    if not url_or_name:
        return ""
    s = url_or_name.strip().lower()
    parsed = urlparse(s if s.startswith("http") else f"https://{s}")
    return parsed.netloc.replace("www.", "") or s


def fetch_one(query: str, max_pages: int = 4) -> list[dict]:
    """Query Google Fact Check Tools for `query`, paginating to max_pages."""
    if not API_KEY:
        raise RuntimeError(
            "GOOGLE_FACTCHECK_API_KEY not set. Add it to .env. "
            "Get a key at console.cloud.google.com → enable 'Fact Check Tools API'."
        )
    out, page_token = [], None
    for page in range(max_pages):
        params = {
            "key": API_KEY,
            "query": query,
            "languageCode": "en",
            "pageSize": PAGE_SIZE,
        }
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(API_URL, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"[error] {query!r} page {page}: HTTP {resp.status_code} {resp.text[:200]}")
            break
        data = resp.json()
        claims = data.get("claims", [])
        out.extend(claims)
        page_token = data.get("nextPageToken")
        print(f"[fetch] {query!r} page {page}: +{len(claims)} (total {len(out)})")
        if not page_token or not claims:
            break
        time.sleep(0.3)  # gentle pacing
    return out


def is_debunked(rating: str) -> bool:
    """Decide whether a ClaimReview textualRating means 'this claim is refuted'."""
    if not rating:
        return False
    rating = rating.strip()
    # Hard reject: explicit affirmation labels ("True", "Mostly True", etc.)
    if AFFIRMING_RATING_RX.match(rating):
        return False
    # Allow: verdict-style words anywhere in the rating
    if DEBUNKED_RATING_RX.search(rating):
        return True
    # Allow: long prose ratings (>40 chars) that contain a negation against the
    # claim — publishers like fullfact.org write the refutation directly into
    # textualRating instead of a verdict label.
    if len(rating) > 40 and re.search(r"\b(no|not|doesn'?t|cannot|isn'?t|aren'?t|wasn'?t|never)\b", rating, re.IGNORECASE):
        return True
    return False


def adapt(raw_claims: list[dict], query_label: str, existing_urls: set[str]) -> list[dict]:
    """Convert Google API claims → claims.json-shaped article records.

    One claim ↔ one ClaimReview ↔ one synthetic 'article' record (because
    Stage 3 keys on (article_url, claim_source) and that mapping is cleanest
    one-to-one for external sources)."""
    out, dropped_offtopic, dropped_undebunked, dropped_dup = [], 0, 0, 0
    for c in raw_claims:
        claim_text = (c.get("text") or "").strip()
        if not claim_text:
            continue
        if not WOMENS_HEALTH_RX.search(claim_text):
            dropped_offtopic += 1
            continue
        for review in c.get("claimReview") or []:
            url = (review.get("url") or "").strip()
            if not url or url in existing_urls:
                dropped_dup += 1
                continue
            rating = (review.get("textualRating") or "").strip()
            if not is_debunked(rating):
                dropped_undebunked += 1
                continue
            publisher = review.get("publisher") or {}
            outlet = domain_of(publisher.get("site") or publisher.get("name") or "")
            if not outlet:
                continue
            existing_urls.add(url)
            out.append({
                "article_url": url,
                "article_title": (review.get("title") or claim_text)[:300],
                "fact_check_outlet": outlet,
                "topic": query_label,
                "publish_date": (review.get("reviewDate") or c.get("claimDate") or "")[:10],
                "claims": [{
                    "claim_text": claim_text,
                    "claim_source": (c.get("claimant") or "").strip() or None,
                    "refutation": f"ClaimReview rating: {rating}",
                    "evidence_sources": [],
                }],
                "extraction_failed": False,
                "_external": True,
                "_external_rating": rating,
            })
    print(f"[adapt] kept {len(out)}, dropped: off-topic={dropped_offtopic}, "
          f"not-debunked={dropped_undebunked}, duplicate-url={dropped_dup}")
    return out


def load_existing_urls() -> set[str]:
    p = Path(INPUT_CORPUS_CLAIMS)
    if not p.exists():
        return set()
    with p.open() as f:
        return {a.get("article_url", "") for a in json.load(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", help="Search phrase (repeat for multiple)")
    ap.add_argument("--default-queries", action="store_true", help=f"Run the {len(DEFAULT_QUERIES)}-phrase default set")
    ap.add_argument("--max-pages", type=int, default=4, help="Pages per query (50 results/page)")
    args = ap.parse_args()

    queries = list(args.query or [])
    if args.default_queries:
        queries.extend(DEFAULT_QUERIES)
    if not queries:
        ap.error("Pass --query <phrase> at least once, or --default-queries")

    existing_urls = load_existing_urls()
    print(f"[init] {len(existing_urls)} existing in-corpus fact-check URLs (will skip duplicates)")

    raw_all, adapted_all = [], []
    for q in queries:
        raw = fetch_one(q, max_pages=args.max_pages)
        raw_all.extend({"_query": q, **c} for c in raw)
        adapted_all.extend(adapt(raw, q, existing_urls))

    Path(OUTPUT_RAW).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_RAW, "w") as f:
        json.dump(raw_all, f, indent=2)
    print(f"[write] {OUTPUT_RAW}  ({len(raw_all)} raw API records)")
    with open(OUTPUT_CLAIMS, "w") as f:
        json.dump(adapted_all, f, indent=2)
    print(f"[write] {OUTPUT_CLAIMS}  ({len(adapted_all)} adapted claim records)")

    print()
    print("=" * 60)
    print(f"Outlets contributing external fact-checks:")
    print("=" * 60)
    by_outlet = {}
    for r in adapted_all:
        by_outlet[r["fact_check_outlet"]] = by_outlet.get(r["fact_check_outlet"], 0) + 1
    for outlet, n in sorted(by_outlet.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {outlet}")
    print()
    print(f"Next step: re-run Stage 3 with the external set merged in:")
    print(f"  python pipeline/stage3_filter.py --extra-input {OUTPUT_CLAIMS}")


if __name__ == "__main__":
    main()
