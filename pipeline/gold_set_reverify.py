"""Re-run Stage 4b's verify() on the gold-set pair_ids only, after a prompt
change, so we can measure the precision delta against the same cloud labels
without re-running the full Stage 4b on all ~3k pairs.

Reads:
- data/gold_set_labeled.csv  (the labeled gold set with pair_ids and the
                              existing ollama_verdict column)
- data/stage4b_verdicts.json (to map pair_id → article_url, claim_id, etc.)
- data/stage4a_candidates.json (to look up claim_text/source/refutation)
- data/articles_classified.csv (to look up article body text)

Writes:
- data/gold_set_labeled_v2.csv  with new column ollama_verdict_v2

Then run:
    python pipeline/gold_set_eval.py --input data/gold_set_labeled_v2.csv \\
        --judge-col cloud_llm_verdict --llm-col ollama_verdict_v2
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from stage4b_verify import verify  # uses the new PROMPT_TEMPLATE

INPUT_LABELED = "data/gold_set_labeled.csv"
OUTPUT_LABELED = "data/gold_set_labeled_v2.csv"
VERDICTS_JSON = "data/stage4b_verdicts.json"
CANDIDATES_JSON = "data/stage4a_candidates.json"
ARTICLES_CSV = "data/articles_classified.csv"

csv.field_size_limit(2**30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=INPUT_LABELED)
    ap.add_argument("--output", default=OUTPUT_LABELED)
    args = ap.parse_args()

    # Load gold set
    with open(args.input, newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []
    print(f"[input] {len(rows)} gold-set rows from {args.input}")

    # Build pair_id → verdict-record lookup (verdicts have article_url + claim_id;
    # gold-set rows have pair_id which is the index into the original verdicts list,
    # but after the audit we filtered the verdicts, so pair_id no longer matches the
    # current index. Match instead on article_url + claim_id present in both.)
    with open(VERDICTS_JSON) as f:
        verdicts = json.load(f)
    verdicts_by_key = {(v["article_url"], v["claim_id"]): v for v in verdicts}

    # Build claim_id → claim lookup
    with open(CANDIDATES_JSON) as f:
        cand = json.load(f)
    claims_by_id = {c["claim_id"]: c for c in cand["claims"]}

    # Build article_url → article lookup
    arts = pd.read_csv(ARTICLES_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    articles_by_url = {r["url"]: r for _, r in arts.iterrows()}

    # Re-verify each gold-set row
    new_verdicts = []
    misses = 0
    for i, row in enumerate(rows):
        url = row.get("article_url")
        # claim_id is in the gold-set CSV via the original ollama_verdict column?
        # No — the CSV doesn't carry claim_id directly. We need to look it up.
        # Strategy: match by (article_url, claim_text) since claim_text IS in the CSV.
        claim_text = row.get("claim_text", "").strip()
        # Find the verdict record matching this article + claim_text
        matching = [v for v in verdicts
                    if v["article_url"] == url and v.get("claim_text", "").strip() == claim_text]
        if not matching:
            print(f"  [miss] row {i}: no verdict record for {url[:60]} / {claim_text[:60]}")
            new_verdicts.append("")
            misses += 1
            continue
        v_rec = matching[0]
        claim = claims_by_id.get(v_rec["claim_id"])
        article = articles_by_url.get(url)
        if claim is None or article is None:
            print(f"  [miss] row {i}: claim_id={v_rec['claim_id']} or article missing")
            new_verdicts.append("")
            misses += 1
            continue
        result = verify(
            claim=claim,
            article_title=article["title"],
            article_outlet=article["media_name"],
            article_text=article["full_text"],
        )
        new_verdicts.append(result["verdict"] if result else "UNKNOWN")
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(rows)}] re-verified")

    # Write output CSV with new column appended
    out_fields = list(fieldnames)
    if "ollama_verdict_v2" not in out_fields:
        out_fields.append("ollama_verdict_v2")
    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for row, nv in zip(rows, new_verdicts):
            row = dict(row)
            row["ollama_verdict_v2"] = nv
            w.writerow(row)
    print()
    print(f"[write] {args.output}  ({len(rows)} rows, {misses} misses)")
    print()
    print("Compare against cloud labels:")
    print(f"  python pipeline/gold_set_eval.py --input {args.output} \\")
    print(f"      --judge-col cloud_llm_verdict --llm-col ollama_verdict_v2")


if __name__ == "__main__":
    main()
