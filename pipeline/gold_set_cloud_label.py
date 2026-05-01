"""Cloud-LLM gold-set labeler. Calls Claude as judge to fill in the
`cloud_llm_verdict` column on a gold-set template produced by gold_set_build.py.

Defaults to claude-opus-4-7 (matches the original 2026-04-28 gold set's judge,
giving apples-to-apples comparison with the historical 90% / 0.84-precision
baseline). Override with --model.

Usage:
    # Smoke test on 5 rows
    python pipeline/gold_set_cloud_label.py --max-rows 5

    # Full run
    python pipeline/gold_set_cloud_label.py

    # Override model
    python pipeline/gold_set_cloud_label.py --model claude-sonnet-4-6

Requires:
    - ANTHROPIC_API_KEY in .env or environment
    - pip install anthropic
"""
import argparse
import asyncio
import csv
import json
import os
import sys
import time

import pandas as pd
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_CONCURRENCY = 12

INPUT_TEMPLATE = "data/gold_set_template_v2.csv"
OUTPUT_LABELED = "data/gold_set_labeled_v2.csv"
ARTICLES_CSV = "data/articles_classified.csv"

csv.field_size_limit(2**30)

JUDGE_SYSTEM_PROMPT = """You are an expert media-analysis judge classifying how news articles handle previously-debunked health claims.

For each (article, claim) pair, decide which of these four categories the article falls into:

1. **carrying** — the article presents the claim as true, endorses it, or repeats it uncritically in a way that could lead a reader to accept it as fact.

2. **debunking** — the article explicitly refutes the claim, citing counter-evidence, experts, or regulators.

3. **neutral_reporting** — the article mentions the claim (e.g. "X said Y") without endorsing or refuting it; purely descriptive — quotes a source making the claim but the article itself takes no position.

4. **irrelevant** — the article does not substantively discuss this specific claim; the topic overlap is incidental, or the claim is mentioned only in passing.

Decision rules:
- Read the article carefully before classifying. The article's *overall posture* toward the claim matters more than any single sentence.
- "Carrying" requires the article to advance, endorse, or amplify the claim. An article that quotes a partisan source making the claim while *also* presenting refutation is NOT carrying — it's debunking or neutral_reporting depending on framing balance.
- The "quote-then-refute" pattern is debunking, not carrying: an article that quotes a claim and then immediately rebuts it via expert sources, regulators, or counter-evidence is debunking that claim.
- "Debunking" requires explicit refutation, not just reporting that the claim is disputed. Look for citations to expert sources, studies, or regulators that contradict the claim.
- "Neutral reporting" is for cases where the article reports on the claim or its source without taking a position. The line between neutral_reporting and irrelevant is whether the article *substantively engages* with the claim (even just to describe it) vs only mentioning it in passing.
- "Irrelevant" is for cases where the search-similarity surfaced the article but the claim isn't actually substantively engaged. Brief mentions in passing don't count as substantive engagement.
- Be strict on "carrying" — partisan framing alone, or quoting a known proponent without endorsement, is not enough.

For each pair, return strict JSON with:
- `verdict`: one of carrying | debunking | neutral_reporting | irrelevant
- `evidence_quote`: a literal verbatim passage from the article body (character-for-character substring) that best supports your verdict, or null if no single passage supports it
- `reasoning`: one sentence justifying the verdict"""


VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["carrying", "debunking", "neutral_reporting", "irrelevant"],
        },
        "evidence_quote": {"type": ["string", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": ["verdict", "evidence_quote", "reasoning"],
    "additionalProperties": False,
}


def build_user_prompt(row, article_text):
    return f"""CLAIM (previously debunked): "{row['claim_text']}"
CLAIM ORIGINATOR: {row.get('claim_source', '(unknown)')}
DEBUNKED BY: {row.get('fact_check_outlet', '(unknown)')} ({row.get('fact_check_url', 'no url')})

Classify how the article below handles this claim.

ARTICLE TITLE: {row['article_title']}
ARTICLE OUTLET: {row['article_outlet']}
ARTICLE TEXT:
\"\"\"{article_text}\"\"\"
"""


async def label_one(client, sem, row, article_text, model):
    async with sem:
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=2000,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": "high",
                    "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
                },
                # Cache the system prompt across calls. Likely below Opus 4.7's
                # 4096-token cache minimum so this is a no-op today, but harmless
                # to include and will start working if the prompt ever grows.
                cache_control={"type": "ephemeral"},
                system=JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(row, article_text)}],
            )
            text = next(b.text for b in response.content if b.type == "text")
            data = json.loads(text)
            return row["pair_id"], data, response.usage
        except Exception as e:
            return row["pair_id"], {"error": f"{type(e).__name__}: {e}"}, None


async def main_async(args):
    client = AsyncAnthropic()  # ANTHROPIC_API_KEY from env

    with open(args.input, newline="") as f:
        rows = list(csv.DictReader(f))

    arts = pd.read_csv(args.articles, dtype=str, keep_default_na=False, encoding="utf-8")
    bodies = {r["url"]: r["full_text"] for _, r in arts.iterrows()}

    # Resume: load existing cloud_llm_verdict values if output exists
    existing = {}
    out_extras = {}  # evidence_quote_cloud, reasoning_cloud
    if os.path.exists(args.output):
        with open(args.output, newline="") as f:
            for r in csv.DictReader(f):
                v = (r.get("cloud_llm_verdict") or "").strip()
                if v:
                    existing[r["pair_id"]] = v
                    out_extras[r["pair_id"]] = {
                        "evidence_quote_cloud": r.get("evidence_quote_cloud", ""),
                        "reasoning_cloud": r.get("reasoning_cloud", ""),
                    }
        print(f"[resume] {len(existing)} rows already labeled in {args.output}")

    todo = [r for r in rows if r["pair_id"] not in existing]
    if args.max_rows:
        todo = todo[:args.max_rows]
    print(f"[todo] {len(todo)}/{len(rows)} rows to label  |  model={args.model}  |  concurrency={args.concurrency}")

    results = {}

    if todo:
        sem = asyncio.Semaphore(args.concurrency)
        tasks = []
        for row in todo:
            body = bodies.get(row["article_url"])
            if body is None:
                print(f"  [skip] no article body: {row['article_url'][:70]}")
                results[row["pair_id"]] = {"error": "no_article_body"}
                continue
            tasks.append(label_one(client, sem, row, body, args.model))

        total_input = total_output = total_cache_read = total_cache_create = 0
        start = time.time()
        completed = 0
        for fut in asyncio.as_completed(tasks):
            pair_id, data, usage = await fut
            results[pair_id] = data
            if usage:
                total_input += usage.input_tokens
                total_output += usage.output_tokens
                total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
                total_cache_create += getattr(usage, "cache_creation_input_tokens", 0) or 0
            completed += 1
            if completed % 5 == 0 or completed == len(tasks):
                elapsed = time.time() - start
                rate = completed / elapsed if elapsed else 0
                hit_pct = (100 * total_cache_read / (total_cache_read + total_input)) if (total_cache_read + total_input) else 0
                print(f"  [{completed}/{len(tasks)}] elapsed {elapsed:.0f}s | {rate:.2f}/s | cache hit ratio: {hit_pct:.0f}%")

        elapsed = time.time() - start
        print()
        print(f"Token usage:")
        print(f"  input (uncached):     {total_input:>10,}")
        print(f"  cache reads:          {total_cache_read:>10,}  (~10% of input cost)")
        print(f"  cache creates:        {total_cache_create:>10,}  (~125% of input cost)")
        print(f"  output:               {total_output:>10,}")
        print(f"  wall clock:           {elapsed:>10.0f}s")

    # Write output (idempotent — re-runs preserve previously labeled rows)
    out_fields = list(rows[0].keys())
    for col in ("cloud_llm_verdict", "evidence_quote_cloud", "reasoning_cloud"):
        if col not in out_fields:
            insert_idx = out_fields.index("pair_id") + 1 if "pair_id" in out_fields else 0
            out_fields.insert(insert_idx, col)

    n_labeled = 0
    n_errors = 0
    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            r_out = dict(r)
            pid = r["pair_id"]
            if pid in existing:
                r_out["cloud_llm_verdict"] = existing[pid]
                r_out["evidence_quote_cloud"] = out_extras[pid]["evidence_quote_cloud"]
                r_out["reasoning_cloud"] = out_extras[pid]["reasoning_cloud"]
                n_labeled += 1
            elif pid in results and "error" not in results[pid]:
                r_out["cloud_llm_verdict"] = results[pid]["verdict"]
                r_out["evidence_quote_cloud"] = results[pid].get("evidence_quote") or ""
                r_out["reasoning_cloud"] = results[pid].get("reasoning", "")
                n_labeled += 1
            else:
                r_out["cloud_llm_verdict"] = ""
                r_out["evidence_quote_cloud"] = ""
                r_out["reasoning_cloud"] = ""
                if pid in results and "error" in results[pid]:
                    n_errors += 1
            w.writerow(r_out)

    print()
    print(f"[write] {args.output}  ({n_labeled}/{len(rows)} labeled, {n_errors} errors)")

    errors = [(pid, r["error"]) for pid, r in results.items() if "error" in r]
    if errors:
        print(f"\n⚠ {len(errors)} errors:")
        for pid, err in errors[:5]:
            print(f"  pair_id={pid}: {err[:160]}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more")

    print()
    print("Next: score against the new pipeline's verdicts:")
    print(f"  python pipeline/gold_set_eval.py --input {args.output} \\")
    print(f"      --judge-col cloud_llm_verdict --llm-col ollama_verdict")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=INPUT_TEMPLATE)
    p.add_argument("--output", default=OUTPUT_LABELED)
    p.add_argument("--articles", default=ARTICLES_CSV)
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Claude model ID (default: {DEFAULT_MODEL})")
    p.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    p.add_argument("--max-rows", type=int, default=None,
                   help="Smoke-test by limiting to N rows")
    args = p.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env or export it.",
              file=sys.stderr)
        sys.exit(1)

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
