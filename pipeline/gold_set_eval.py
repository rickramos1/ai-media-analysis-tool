"""Score Stage 4b LLM verdicts against the human-labeled gold set (BACKLOG #6).

Reads a labeled CSV from `gold_set_build.py` (after a reviewer has filled in
the `human_verdict` column). Reports a confusion matrix, per-class
precision / recall / F1, overall accuracy, and lists the misclassified
pairs — most usefully, `carrying` false-positives (LLM said carrying, human
said otherwise), since those would taint published findings.

Usage:
    python pipeline/gold_set_eval.py
    python pipeline/gold_set_eval.py --input data/gold_set_labeled.csv

Writes per-class metrics to data/gold_set_metrics.json for diff'ing across runs.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

INPUT_LABELED = "data/gold_set_labeled.csv"
OUTPUT_METRICS = "data/gold_set_metrics.json"

VERDICT_CLASSES = ["carrying", "debunking", "neutral_reporting", "irrelevant"]

# Column-name fallbacks. The build script writes `human_verdict` / `llm_verdict`,
# but reviewers sometimes rename them to make the labeling source explicit
# (e.g. `cloud_llm_verdict` when Claude was used as judge, `ollama_verdict` for
# the Stage 4b qwen3 output). Auto-detect either; --judge-col / --llm-col override.
JUDGE_COL_FALLBACKS = ["human_verdict", "cloud_llm_verdict", "judge_verdict"]
LLM_COL_FALLBACKS = ["llm_verdict", "ollama_verdict", "stage4b_verdict"]


def safe_div(num, denom):
    return num / denom if denom else 0.0


def pick_column(fieldnames, fallbacks, override, role):
    if override:
        if override not in fieldnames:
            raise SystemExit(f"--{role}-col {override!r} not in CSV columns: {fieldnames}")
        return override
    for c in fallbacks:
        if c in fieldnames:
            return c
    raise SystemExit(
        f"Could not find a {role} column. Tried: {fallbacks}. "
        f"Pass --{role}-col explicitly. CSV has: {fieldnames}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=INPUT_LABELED)
    ap.add_argument("--output", default=OUTPUT_METRICS)
    ap.add_argument("--show-misses", type=int, default=10,
                    help="How many misclassified pairs to print per class")
    ap.add_argument("--judge-col", default=None,
                    help=f"Column with the ground-truth label. Auto-detects from {JUDGE_COL_FALLBACKS}.")
    ap.add_argument("--llm-col", default=None,
                    help=f"Column with the verdict to score. Auto-detects from {LLM_COL_FALLBACKS}.")
    args = ap.parse_args()

    if not Path(args.input).exists():
        ap.error(f"{args.input} not found. Run gold_set_build.py first, "
                 f"then label and save as data/gold_set_labeled.csv")

    with open(args.input, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    judge_col = pick_column(fieldnames, JUDGE_COL_FALLBACKS, args.judge_col, "judge")
    llm_col = pick_column(fieldnames, LLM_COL_FALLBACKS, args.llm_col, "llm")
    print(f"[input] judge column = {judge_col!r}, llm column = {llm_col!r}")

    labeled, skipped, blank = [], 0, 0
    for r in rows:
        h = (r.get(judge_col) or "").strip().lower()
        if not h:
            blank += 1
            continue
        if h == "skip":
            skipped += 1
            continue
        if h not in VERDICT_CLASSES:
            print(f"[warn] pair_id={r.get('pair_id')}: unknown {judge_col} {h!r} — skipping")
            continue
        labeled.append(r)

    total = len(rows)
    print(f"[input] {total} total rows: {len(labeled)} labeled, {skipped} skipped, {blank} blank")
    if not labeled:
        print(f"[error] nothing to evaluate. Fill in {judge_col} for at least one row.")
        return

    # Confusion matrix: confusion[judge][llm] = count
    confusion = defaultdict(lambda: Counter())
    for r in labeled:
        h = r[judge_col].strip().lower()
        l = (r.get(llm_col) or "").strip().lower()
        confusion[h][l] += 1

    correct = sum(confusion[c][c] for c in VERDICT_CLASSES)
    accuracy = safe_div(correct, len(labeled))

    # Per-class precision (of LLM-predicted X, how many were actually X) and
    # recall (of actual X, how many did the LLM catch).
    per_class = {}
    for cls in VERDICT_CLASSES:
        tp = confusion[cls][cls]
        fp = sum(confusion[h][cls] for h in VERDICT_CLASSES if h != cls)
        fn = sum(confusion[cls][l] for l in VERDICT_CLASSES if l != cls)
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        per_class[cls] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": tp + fn,
        }

    # Print confusion matrix
    print()
    print("=" * 70)
    print(f"Confusion matrix  (rows={judge_col}, cols={llm_col})")
    print("=" * 70)
    col_w = 14
    print(f"{'':20s}" + "".join(f"{c[:col_w-1]:>{col_w}}" for c in VERDICT_CLASSES) + f"{'TOTAL':>{col_w}}")
    for h in VERDICT_CLASSES:
        row = [confusion[h][l] for l in VERDICT_CLASSES]
        total_h = sum(row)
        print(f"{h:20s}" + "".join(f"{n:>{col_w}d}" for n in row) + f"{total_h:>{col_w}d}")
    col_totals = [sum(confusion[h][l] for h in VERDICT_CLASSES) for l in VERDICT_CLASSES]
    print(f"{'LLM TOTAL':20s}" + "".join(f"{n:>{col_w}d}" for n in col_totals) + f"{len(labeled):>{col_w}d}")

    # Per-class metrics
    print()
    print("=" * 70)
    print(f"Per-class metrics  (overall accuracy = {accuracy:.1%})")
    print("=" * 70)
    print(f"{'class':22s} {'precision':>10s} {'recall':>8s} {'f1':>6s} {'support':>8s}")
    for cls in VERDICT_CLASSES:
        m = per_class[cls]
        print(f"{cls:22s} {m['precision']:>10.3f} {m['recall']:>8.3f} "
              f"{m['f1']:>6.3f} {m['support']:>8d}")

    # The sharp end: carrier false-positives. These are the pairs the
    # pipeline would publish as misinfo carriers but the reviewer disagrees.
    carrier_fp = [r for r in labeled
                  if (r.get(llm_col) or "").strip().lower() == "carrying"
                  and r[judge_col].strip().lower() != "carrying"]
    if carrier_fp:
        print()
        print("=" * 70)
        print(f"⚠ {len(carrier_fp)} carrier false-positives "
              f"({llm_col} said 'carrying', {judge_col} disagreed)")
        print("=" * 70)
        for r in carrier_fp[:args.show_misses]:
            print(f"  pair_id={r['pair_id']}  judge={r[judge_col]:18s}  "
                  f"sim={r.get('similarity')}")
            print(f"    article: {r.get('article_outlet')} — {(r.get('article_title') or '')[:80]}")
            print(f"    claim:   {(r.get('claim_text') or '')[:100]}")
            note = (r.get('notes') or '').strip()
            if note:
                print(f"    note:    {note}")
        if len(carrier_fp) > args.show_misses:
            print(f"  … and {len(carrier_fp) - args.show_misses} more")

    # Carrier false-negatives — pairs the LLM let through but the reviewer
    # thinks were actually carrying. Worth seeing too.
    carrier_fn = [r for r in labeled
                  if (r.get(llm_col) or "").strip().lower() != "carrying"
                  and r[judge_col].strip().lower() == "carrying"]
    if carrier_fn:
        print()
        print("=" * 70)
        print(f"⚠ {len(carrier_fn)} carrier false-negatives "
              f"({judge_col} said 'carrying', {llm_col} said otherwise)")
        print("=" * 70)
        for r in carrier_fn[:args.show_misses]:
            print(f"  pair_id={r['pair_id']}  llm={r.get(llm_col):18s}  "
                  f"sim={r.get('similarity')}")
            print(f"    article: {r.get('article_outlet')} — {(r.get('article_title') or '')[:80]}")
            print(f"    claim:   {(r.get('claim_text') or '')[:100]}")
            note = (r.get('notes') or '').strip()
            if note:
                print(f"    note:    {note}")
        if len(carrier_fn) > args.show_misses:
            print(f"  … and {len(carrier_fn) - args.show_misses} more")

    # Persist for diff'ing across runs
    metrics = {
        "input_file": args.input,
        "n_labeled": len(labeled),
        "n_skipped": skipped,
        "n_blank": blank,
        "accuracy": round(accuracy, 4),
        "per_class": per_class,
        "carrier_false_positives": len(carrier_fp),
        "carrier_false_negatives": len(carrier_fn),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(metrics, f, indent=2)
    print()
    print(f"[write] {args.output}")


if __name__ == "__main__":
    main()
