"""Re-extract evidence_quote for Stage 4b carrying verdicts whose original
quote is not a literal substring of the article (~29% of carriers per the
substring audit).

The carrier *verdicts* are kept as-is — only the quote is re-fetched.
Strict prompt: "literal verbatim passage only, or null." Schema-constrained
output. Substring validation after each call. One retry on failure with
explicit feedback. Final fallback: null with audit flag.

Backups stage4b_verdicts.json before any writes. Idempotent — re-runs only
target verdicts whose current quote still fails validation.

Usage:
    # Smoke test on 5 affected verdicts, no write
    python pipeline/stage4b_quote_reextract.py --max-rows 5 --no-write

    # Full re-extraction
    python pipeline/stage4b_quote_reextract.py

    # Then regen FINDINGS
    python pipeline/stage5_report.py
"""
import argparse
import json
import os
import shutil
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from stage4b_verify import quote_in_article  # reuse the validator

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_PARALLEL = int(os.environ.get("OLLAMA_PARALLEL", "4"))

VERDICTS_JSON = "data/stage4b_verdicts.json"
ARTICLES_CSV = "data/articles_classified.csv"

QUOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence_quote": {"type": ["string", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": ["evidence_quote", "reasoning"],
}

EXTRACT_PROMPT = """/no_think
You previously classified this article as CARRYING the following claim. Your task now is to find a LITERAL VERBATIM passage from the article body that demonstrates the article presents the claim as true.

CLAIM: "{claim_text}"
CLAIM ORIGINATOR: {claim_source}

STRICT RULES:
- The `evidence_quote` field MUST be a literal substring of the article body — copied character-for-character.
- Do NOT abridge with "..." or "[...]".
- Do NOT rephrase, summarize, or combine non-adjacent sentences.
- Do NOT change quotation marks, capitalization, or punctuation.
- If no single literal passage from the article clearly supports the carrying verdict, output null.
- Prefer 1-2 complete sentences over fragments.

Return JSON.

ARTICLE TITLE: {article_title}
ARTICLE TEXT:
\"\"\"{article_text}\"\"\"
"""

RETRY_PROMPT = """/no_think
Your previous extraction returned a quote that was NOT found in the article body. Either find a DIFFERENT literal passage from the article that supports the carrying verdict, or output null if no such passage exists.

CLAIM: "{claim_text}"
PREVIOUS BAD QUOTE (not in article): "{bad_quote}"

Same strict rules: literal substring only, no abridgment, no paraphrase.

ARTICLE TITLE: {article_title}
ARTICLE TEXT:
\"\"\"{article_text}\"\"\"
"""


def _extract_json(s):
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except json.JSONDecodeError:
        return None


def call_llm(prompt, num_predict=600):
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": QUOTE_SCHEMA,
        "options": {"temperature": 0, "num_predict": num_predict, "num_ctx": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8")).get("response", "")


def reextract(verdict, article_text, article_title):
    """Returns (new_quote: str|None, reasoning: str, status: str).

    status: "extracted_clean" | "extracted_after_retry" | "nulled_after_retries" | "llm_failed"
    """
    # Attempt 1
    prompt = EXTRACT_PROMPT.format(
        claim_text=verdict["claim_text"],
        claim_source=verdict.get("claim_source", "(unknown)"),
        article_title=article_title,
        article_text=article_text,
    )
    try:
        resp = call_llm(prompt)
        parsed = _extract_json(resp)
        if parsed:
            quote = parsed.get("evidence_quote")
            reasoning = str(parsed.get("reasoning", "")).strip()
            if quote is None:
                # Model gave up cleanly — accept the null
                return None, reasoning, "nulled_by_llm"
            if quote_in_article(quote, article_text):
                return quote, reasoning, "extracted_clean"
            # Bad quote on attempt 1 — retry with feedback
            bad_quote_1 = quote
        else:
            bad_quote_1 = ""
            reasoning = ""
    except Exception:
        return None, "llm_call_failed", "llm_failed"

    # Attempt 2
    prompt2 = RETRY_PROMPT.format(
        claim_text=verdict["claim_text"],
        bad_quote=bad_quote_1[:300],
        article_title=article_title,
        article_text=article_text,
    )
    try:
        resp = call_llm(prompt2)
        parsed = _extract_json(resp)
        if parsed:
            quote = parsed.get("evidence_quote")
            reasoning2 = str(parsed.get("reasoning", "")).strip()
            if quote is None:
                return None, reasoning2 or reasoning, "nulled_by_llm"
            if quote_in_article(quote, article_text):
                return quote, reasoning2 or reasoning, "extracted_after_retry"
            # Still bad — null with audit
            return None, reasoning2 or reasoning, "nulled_after_retries"
    except Exception:
        pass

    return None, reasoning if 'reasoning' in dir() else "", "nulled_after_retries"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=VERDICTS_JSON)
    ap.add_argument("--articles", default=ARTICLES_CSV)
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Process only N affected verdicts (smoke test)")
    ap.add_argument("--no-write", action="store_true",
                    help="Compute new quotes but don't write back to verdicts JSON")
    args = ap.parse_args()

    # Backup
    backup_path = f"data/backups/stage4b_verdicts.json.bak.quotereextract.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy(args.input, backup_path)
    print(f"[backup] {args.input} → {backup_path}")

    # Load
    with open(args.input) as f:
        verdicts = json.load(f)
    arts = pd.read_csv(args.articles, dtype=str, keep_default_na=False, encoding="utf-8")
    articles_by_url = {r["url"]: r for _, r in arts.iterrows()}

    carrying = [v for v in verdicts if v.get("verdict") == "carrying"]
    affected = []
    for v in carrying:
        q = v.get("evidence_quote")
        if not q or len(q.strip()) < 12:
            continue  # already null or too short to validate
        article = articles_by_url.get(v["article_url"])
        if article is None:
            continue
        if not quote_in_article(q, article["full_text"]):
            affected.append(v)

    print(f"[input] {len(carrying)} carrying verdicts, {len(affected)} have hallucinated quotes")
    if args.max_rows:
        affected = affected[:args.max_rows]
        print(f"[smoke] limited to first {len(affected)}")
    if not affected:
        print("[done] nothing to re-extract")
        return

    # Re-extract in parallel
    counts = {"extracted_clean": 0, "extracted_after_retry": 0,
              "nulled_by_llm": 0, "nulled_after_retries": 0, "llm_failed": 0}
    start = time.time()

    def work(v):
        article = articles_by_url[v["article_url"]]
        new_quote, reasoning, status = reextract(v, article["full_text"], article["title"])
        return v, new_quote, reasoning, status

    with ThreadPoolExecutor(max_workers=OLLAMA_PARALLEL) as ex:
        futures = [ex.submit(work, v) for v in affected]
        done = 0
        for fut in as_completed(futures):
            v, new_quote, reasoning, status = fut.result()
            counts[status] += 1
            # Preserve original quote for audit, then update
            if "evidence_quote_original_hallucinated" not in v:
                v["evidence_quote_original_hallucinated"] = v.get("evidence_quote")
            v["evidence_quote"] = new_quote
            v["evidence_quote_reextract_status"] = status
            v["evidence_quote_reextract_reasoning"] = reasoning
            done += 1
            if done % 10 == 0 or done == len(affected):
                elapsed = time.time() - start
                rate = done / elapsed if elapsed else 0
                remaining = (len(affected) - done) / rate if rate else 0
                print(f"  [{done}/{len(affected)}] elapsed {elapsed:.0f}s | remaining {remaining:.0f}s | "
                      f"{rate:.2f}/s | clean={counts['extracted_clean']} retry={counts['extracted_after_retry']} "
                      f"nulled={counts['nulled_by_llm']+counts['nulled_after_retries']} failed={counts['llm_failed']}")

    print()
    print("=" * 60)
    print("Re-extraction results")
    print("=" * 60)
    print(f"  clean (literal quote on attempt 1):     {counts['extracted_clean']}")
    print(f"  recovered (literal quote after retry):  {counts['extracted_after_retry']}")
    print(f"  nulled by LLM (no quote available):     {counts['nulled_by_llm']}")
    print(f"  nulled after 2 hallucinated retries:    {counts['nulled_after_retries']}")
    print(f"  LLM call failed:                        {counts['llm_failed']}")
    print()
    real_quotes = counts['extracted_clean'] + counts['extracted_after_retry']
    null_quotes = counts['nulled_by_llm'] + counts['nulled_after_retries']
    print(f"  net: {real_quotes} verdicts now have verifiable literal quotes "
          f"(was {len(affected)} hallucinated)")
    print(f"  net: {null_quotes} verdicts now have null evidence_quote")

    if not args.no_write:
        with open(args.input, "w") as f:
            json.dump(verdicts, f, indent=2)
        print(f"\n[write] {args.input}")
        print("\nNext: regenerate FINDINGS")
        print("  python pipeline/stage5_report.py")
    else:
        print("\n[no-write] skipped writing back")


if __name__ == "__main__":
    main()
