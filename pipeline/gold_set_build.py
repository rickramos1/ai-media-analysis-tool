"""Build a stratified Stage 4b gold-set template for human labeling (BACKLOG #6).

Stage 4b emits per-pair verdicts in `data/stage4b_verdicts.json` but the LLM's
precision against ground truth has never been measured. This script samples
N pairs per verdict class into a CSV with a blank `human_verdict` column.
A reviewer fills it in; `gold_set_eval.py` then reports per-class precision /
recall / confusion matrix.

Stratifying by verdict (rather than uniform random) ensures we get enough
`carrying` pairs to estimate carrier precision — the metric that matters
most for publication.

Usage:
    python pipeline/gold_set_build.py                    # 25 per class, seed 42
    python pipeline/gold_set_build.py --per-class 50     # 50 per class
    python pipeline/gold_set_build.py --seed 7
"""
import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

INPUT_VERDICTS = "data/stage4b_verdicts.json"
OUTPUT_TEMPLATE = "data/gold_set_template.csv"

VERDICT_CLASSES = ["carrying", "debunking", "neutral_reporting", "irrelevant"]

# Columns the reviewer sees. `human_verdict` and `notes` are blank for them
# to fill in. Everything else is reference context.
COLUMNS = [
    "pair_id",
    "human_verdict",       # ← reviewer fills in: carrying|debunking|neutral_reporting|irrelevant|skip
    "notes",               # ← reviewer fills in (free text, optional)
    "llm_verdict",
    "similarity",
    "article_outlet",
    "article_url",
    "article_title",
    "article_topic",
    "claim_text",
    "claim_source",
    "fact_check_outlet",
    "fact_check_url",
    "evidence_quote",
    "llm_reasoning",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=25,
                    help="Pairs to sample per verdict class (default 25 → 100 total)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--input", default=INPUT_VERDICTS)
    ap.add_argument("--output", default=OUTPUT_TEMPLATE)
    args = ap.parse_args()

    random.seed(args.seed)

    with open(args.input) as f:
        verdicts = json.load(f)

    # Assign stable pair_id (index into source file) so re-builds with same seed
    # produce comparable label sets.
    for i, v in enumerate(verdicts):
        v["_pair_id"] = i

    by_class = defaultdict(list)
    for v in verdicts:
        cls = v.get("verdict")
        if cls in VERDICT_CLASSES:
            by_class[cls].append(v)

    print(f"[input] {len(verdicts)} total pairs from {args.input}")
    for cls in VERDICT_CLASSES:
        print(f"  {cls:20s} {len(by_class[cls]):5d}")

    sampled = []
    for cls in VERDICT_CLASSES:
        pool = by_class[cls]
        if not pool:
            print(f"[warn] no pairs of class {cls!r} — skipping")
            continue
        n = min(args.per_class, len(pool))
        if n < args.per_class:
            print(f"[warn] only {n} {cls!r} pairs available (asked for {args.per_class})")
        sampled.extend(random.sample(pool, n))

    random.shuffle(sampled)  # interleave classes so reviewer can't infer LLM verdict from order

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for v in sampled:
            w.writerow({
                "pair_id": v["_pair_id"],
                "human_verdict": "",
                "notes": "",
                "llm_verdict": v.get("verdict"),
                "similarity": round(v.get("similarity") or 0, 4),
                "article_outlet": v.get("article_outlet"),
                "article_url": v.get("article_url"),
                "article_title": v.get("article_title"),
                "article_topic": v.get("article_topic"),
                "claim_text": v.get("claim_text"),
                "claim_source": v.get("claim_source"),
                "fact_check_outlet": v.get("fact_check_outlet"),
                "fact_check_url": v.get("fact_check_url"),
                "evidence_quote": v.get("evidence_quote") or "",
                "llm_reasoning": v.get("reasoning") or "",
            })

    print()
    print(f"[write] {args.output}  ({len(sampled)} pairs)")
    print()
    print("Reviewer instructions:")
    print("  • Open the CSV, read each row's article + claim + evidence_quote.")
    print("  • Fill `human_verdict` with one of: carrying | debunking | neutral_reporting | irrelevant | skip")
    print("  • `skip` = ambiguous; excluded from metrics.")
    print("  • Save as data/gold_set_labeled.csv, then run:")
    print("      python pipeline/gold_set_eval.py")


if __name__ == "__main__":
    main()
