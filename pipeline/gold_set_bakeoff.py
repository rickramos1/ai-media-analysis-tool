"""Stage 4b model bake-off. Runs verify() against the 100-row gold set with
each candidate model in turn, then scores each model's output against the
cloud-LLM judge labels.

Reads:
- data/gold_set_labeled_v2.csv  (has cloud_llm_verdict from gold_set_cloud_label.py
                                  plus llm_verdict from the qwen3 baseline)
- data/articles_classified.csv  (article bodies)
- data/stage4a_candidates.json  (claim metadata)

Writes:
- data/gold_set_bakeoff_results.csv  (one row per (model, pair_id), with verdict)
- data/gold_set_bakeoff_summary.json (per-model metrics)

Prints a comparison table at the end.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from stage4b_verify import (PROMPT_TEMPLATE, VERDICT_SCHEMA, OLLAMA_HOST,
                             _extract_json, VALID_VERDICTS, quote_in_article)

load_dotenv()

GOLD_LABELED = "data/gold_set_labeled_v2.csv"
ARTICLES_CSV = "data/articles_classified.csv"
CANDIDATES_JSON = "data/stage4a_candidates.json"
RESULTS_CSV = "data/gold_set_bakeoff_results.csv"
SUMMARY_JSON = "data/gold_set_bakeoff_summary.json"

# Default field. qwen3:14b is the incumbent and is already scored in the gold-set
# CSV's `llm_verdict` column, so we re-run it here too as a sanity check that
# the bake-off harness produces the same output as Stage 4b.
DEFAULT_MODELS = [
    "qwen3:14b",
    "phi4:14b",
    "phi4-reasoning:latest",
    "gemma3:12b",
    "gpt-oss-safeguard:latest",
]
PARALLEL = 4
csv.field_size_limit(2**30)


def verify_with_model(model, claim, article_title, article_outlet, article_text,
                       max_retries=3, timeout=600):
    """Like stage4b_verify.verify() but with the model name as a parameter."""
    prompt = PROMPT_TEMPLATE.format(
        claim_text=claim["claim_text"],
        claim_source=claim["claim_source"],
        fact_check_outlet=claim["fact_check_outlet"],
        refutation=claim.get("refutation", ""),
        article_title=article_title,
        article_outlet=article_outlet,
        article_text=article_text,
    )
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": VERDICT_SCHEMA,
        "options": {"temperature": 0, "num_predict": 600, "num_ctx": 8192},
    }).encode("utf-8")

    for _ in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
            parsed = _extract_json(json.loads(body).get("response", ""))
            if not parsed:
                continue
            verdict = str(parsed.get("verdict", "")).strip().lower()
            if verdict not in VALID_VERDICTS:
                continue
            return {
                "verdict": verdict,
                "evidence_quote": parsed.get("evidence_quote"),
                "reasoning": str(parsed.get("reasoning", "")).strip(),
            }
        except Exception as e:
            err = e
            continue
    return None


def load_inputs():
    with open(GOLD_LABELED, newline="") as f:
        gold = list(csv.DictReader(f))
    with open(CANDIDATES_JSON) as f:
        cand = json.load(f)
    claims_by_id = {c["claim_id"]: c for c in cand["claims"]}
    arts = pd.read_csv(ARTICLES_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    articles_by_url = {r["url"]: r for _, r in arts.iterrows()}

    # Map gold-set rows to (claim, article) — claim_id isn't in the CSV; look up
    # by (article_url, claim_text) against the candidates.
    enriched = []
    misses = 0
    for r in gold:
        url = r["article_url"]
        claim_text = r["claim_text"].strip()
        # Find claim_id from candidates that matches the gold-set claim_text
        candidate_claim = None
        for c in cand["claims"]:
            if c.get("claim_text", "").strip() == claim_text:
                candidate_claim = c
                break
        article = articles_by_url.get(url)
        if candidate_claim is None or article is None:
            misses += 1
            continue
        enriched.append((r, candidate_claim, article))
    if misses:
        print(f"[warn] {misses} gold-set rows could not be enriched (claim or article missing)")
    return enriched


def run_one_model(model, enriched, parallel=PARALLEL):
    """Run verify() against all gold-set rows for one model. Returns dict of pair_id → result."""
    results = {}
    start = time.time()

    def work(item):
        gold_row, claim, article = item
        result = verify_with_model(
            model=model,
            claim=claim,
            article_title=article["title"],
            article_outlet=article["media_name"],
            article_text=article["full_text"],
        )
        return gold_row["pair_id"], result

    print(f"\n[run] {model}  ({len(enriched)} rows, parallel={parallel})")
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = [ex.submit(work, item) for item in enriched]
        completed = 0
        for fut in as_completed(futs):
            pair_id, result = fut.result()
            results[pair_id] = result
            completed += 1
            if completed % 20 == 0 or completed == len(enriched):
                elapsed = time.time() - start
                rate = completed / elapsed if elapsed else 0
                eta = (len(enriched) - completed) / rate if rate else 0
                print(f"  [{completed}/{len(enriched)}] elapsed {elapsed:.0f}s | rate {rate:.2f}/s | ETA {eta:.0f}s")

    parse_failures = sum(1 for r in results.values() if r is None)
    elapsed = time.time() - start
    print(f"  done in {elapsed:.0f}s, {parse_failures} parse failures")
    return results


def confusion_matrix(judge_col, pred_col, rows):
    """Build 4x4 confusion matrix and per-class metrics."""
    classes = ["carrying", "debunking", "neutral_reporting", "irrelevant"]
    matrix = {j: {p: 0 for p in classes + [None]} for j in classes}
    n_total = 0
    n_correct = 0
    for r in rows:
        j = (r.get(judge_col) or "").strip().lower()
        p = (r.get(pred_col) or "").strip().lower() or None
        if j not in classes:
            continue
        if p is not None and p not in classes:
            p = None
        matrix[j][p] = matrix[j].get(p, 0) + 1
        n_total += 1
        if j == p:
            n_correct += 1
    accuracy = n_correct / n_total if n_total else 0.0
    # Per-class precision / recall
    per_class = {}
    for c in classes:
        tp = matrix[c][c]
        fp = sum(matrix[other][c] for other in classes if other != c)
        fn = sum(matrix[c][other] for other in classes + [None] if other != c)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class[c] = {"precision": round(prec, 3), "recall": round(rec, 3),
                        "f1": round(f1, 3), "support": tp + fn}
    return {"accuracy": round(accuracy, 3), "n": n_total, "per_class": per_class,
            "matrix": matrix}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Smoke-test mode")
    ap.add_argument("--parallel", type=int, default=PARALLEL)
    args = ap.parse_args()

    enriched = load_inputs()
    if args.max_rows:
        enriched = enriched[:args.max_rows]
    print(f"[input] {len(enriched)} gold-set rows")

    # Run each model
    all_results = {}
    for model in args.models:
        all_results[model] = run_one_model(model, enriched, parallel=args.parallel)

    # Build per-row results: align by pair_id
    gold_rows = {r["pair_id"]: r for r, _, _ in enriched}
    bakeoff_rows = []
    for pid, gold in gold_rows.items():
        out = {
            "pair_id": pid,
            "cloud_llm_verdict": gold.get("cloud_llm_verdict", ""),
            "article_outlet": gold.get("article_outlet", ""),
            "article_title": gold.get("article_title", ""),
            "claim_text": gold.get("claim_text", ""),
        }
        for model in args.models:
            r = all_results[model].get(pid)
            slug = model.replace(":", "_").replace("/", "_")
            out[f"verdict__{slug}"] = (r["verdict"] if r else "PARSE_FAIL")
            out[f"quote__{slug}"] = (r.get("evidence_quote") if r else "") or ""
        bakeoff_rows.append(out)

    # Write results CSV
    fields = list(bakeoff_rows[0].keys())
    with open(RESULTS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(bakeoff_rows)
    print(f"\n[write] {RESULTS_CSV}")

    # Compute metrics per model
    summary = {}
    for model in args.models:
        slug = model.replace(":", "_").replace("/", "_")
        m = confusion_matrix("cloud_llm_verdict", f"verdict__{slug}", bakeoff_rows)
        summary[model] = m

    with open(SUMMARY_JSON, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[write] {SUMMARY_JSON}")

    # Comparison table
    print("\n" + "=" * 100)
    print("Bake-off results (vs cloud_llm_verdict on the same 100-row gold set)")
    print("=" * 100)
    print(f"{'model':<32}{'acc':>8}{'carrier P':>12}{'carrier R':>12}{'carrier F1':>12}{'debunk F1':>12}{'irrel F1':>12}")
    print("-" * 100)
    for model, m in summary.items():
        pc = m["per_class"]
        print(f"{model:<32}{m['accuracy']:>8.3f}"
              f"{pc['carrying']['precision']:>12.3f}"
              f"{pc['carrying']['recall']:>12.3f}"
              f"{pc['carrying']['f1']:>12.3f}"
              f"{pc['debunking']['f1']:>12.3f}"
              f"{pc['irrelevant']['f1']:>12.3f}")
    print()


if __name__ == "__main__":
    main()
