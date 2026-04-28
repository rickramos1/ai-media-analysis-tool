"""Post-processing refutation check on Stage 4b's carrying verdicts.

The Stage 4b carrier verdict has a measured 0.84 precision; the dominant
false-positive pattern is "quote-then-refute" — the article quotes the
claim AND rebuts it elsewhere in the body, but the 4-way classifier
misses the rebuttal.

This script does a SECOND, focused yes/no pass over each `carrying`
verdict. The prompt asks one specific question: does the article contain
direct refutation? If YES with a quote, the verdict is demoted to
`debunking` (or `neutral_reporting` if the refutation is mild).

Design notes:
- Only touches `carrying` verdicts. Other classes are not re-examined.
- Uses the same qwen3:14b model — same blindspot risk, but the focused
  prompt structure puts the refutation question front-and-center, which
  may help where the 4-way classification did not.
- Writes the original verdict to `verdict_pre_refute_check` so the change
  is auditable and reversible.
- Safe to re-run; idempotent if all carrying verdicts already have the
  audit field.

Usage:
    # Backup first (script also writes its own backup)
    python pipeline/stage4b_refute_check.py
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

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_PARALLEL = int(os.environ.get("OLLAMA_PARALLEL", "4"))

VERDICTS_JSON = "data/stage4b_verdicts.json"
ARTICLES_CSV = "data/articles_classified.csv"

REFUTE_PROMPT = """/no_think
You are checking whether a news article contains DIRECT refutation of a specific previously-debunked claim.

CLAIM (previously debunked): "{claim_text}"
CLAIM ORIGINATOR: {claim_source}

Read the article below. Answer ONE question: does the article contain DIRECT refutation of this claim — meaning any of the following:

(a) A counter-quote from a doctor, scientist, regulator, fact-checker, or recognized expert that contradicts the claim
(b) Specific contradicting statistics or studies cited within the article
(c) The author or another speaker explicitly disputing or correcting the claim with substantive evidence

A bare "critics say" or "some disagree" gesture without substance does NOT count as refutation.

Return ONLY a JSON object:
{{
  "refutation_present": true | false,
  "refutation_quote": "<exact passage from article that refutes the claim, or null>",
  "reasoning": "<one sentence>"
}}

ARTICLE TITLE: {article_title}
ARTICLE TEXT:
\"\"\"{article_text}\"\"\"
"""


def call_llm(prompt, num_predict=600):
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
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


def extract_json(s):
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except json.JSONDecodeError:
        return None


def check_refutation(verdict, article_text, article_title, max_retries=3):
    """Returns (refutation_present: bool, refutation_quote: str|None, reasoning: str) or None on hard failure."""
    prompt = REFUTE_PROMPT.format(
        claim_text=verdict["claim_text"],
        claim_source=verdict.get("claim_source", "(unknown)"),
        article_title=article_title,
        article_text=article_text,
    )
    for _ in range(max_retries):
        try:
            resp = call_llm(prompt)
            parsed = extract_json(resp)
            if not parsed or "refutation_present" not in parsed:
                continue
            return (
                bool(parsed["refutation_present"]),
                parsed.get("refutation_quote"),
                str(parsed.get("reasoning", "")).strip(),
            )
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=VERDICTS_JSON)
    ap.add_argument("--articles", default=ARTICLES_CSV)
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Process only N carrying verdicts (smoke test)")
    ap.add_argument("--no-write", action="store_true",
                    help="Compute the demotions but don't write back to verdicts JSON")
    args = ap.parse_args()

    # Backup
    backup_path = f"data/backups/stage4b_verdicts.json.bak.refute.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy(args.input, backup_path)
    print(f"[backup] {args.input} → {backup_path}")

    # Load verdicts
    with open(args.input) as f:
        verdicts = json.load(f)
    carrying = [v for v in verdicts if v.get("verdict") == "carrying"]
    print(f"[input] {len(verdicts)} total verdicts, {len(carrying)} carrying")

    # Filter out ones already audited (idempotency)
    pending = [v for v in carrying if "verdict_pre_refute_check" not in v]
    print(f"[skip-audited] {len(carrying) - len(pending)} already audited; {len(pending)} pending")

    if args.max_rows:
        pending = pending[:args.max_rows]
        print(f"[smoke] limited to first {len(pending)} pending")

    if not pending:
        print("[done] nothing to do")
        return

    # Article body lookup
    arts = pd.read_csv(args.articles, dtype=str, keep_default_na=False, encoding="utf-8")
    articles_by_url = {r["url"]: r for _, r in arts.iterrows()}

    demoted = []
    kept = []
    failed = []
    start = time.time()

    def work(v):
        article = articles_by_url.get(v["article_url"])
        if article is None:
            return v, "missing_article", None, None, None
        result = check_refutation(v, article["full_text"], article["title"])
        if result is None:
            return v, "llm_failed", None, None, None
        present, quote, reasoning = result
        return v, "ok", present, quote, reasoning

    with ThreadPoolExecutor(max_workers=OLLAMA_PARALLEL) as ex:
        futures = [ex.submit(work, v) for v in pending]
        done = 0
        for fut in as_completed(futures):
            v, status, present, quote, reasoning = fut.result()
            done += 1
            if status != "ok":
                failed.append((v, status))
                continue
            v["verdict_pre_refute_check"] = "carrying"
            v["refute_check_quote"] = quote
            v["refute_check_reasoning"] = reasoning
            if present:
                v["verdict"] = "debunking"
                demoted.append(v)
            else:
                kept.append(v)
            if done % 10 == 0 or done == len(pending):
                elapsed = time.time() - start
                rate = done / elapsed if elapsed else 0
                remaining = (len(pending) - done) / rate if rate else 0
                print(f"  [{done}/{len(pending)}] elapsed {elapsed:.0f}s | remaining {remaining:.0f}s | "
                      f"{rate:.2f}/s | demoted {len(demoted)}, kept {len(kept)}, failed {len(failed)}")

    print()
    print("=" * 60)
    print(f"Refutation-check results")
    print("=" * 60)
    print(f"  demoted to debunking: {len(demoted)}")
    print(f"  kept as carrying:     {len(kept)}")
    print(f"  failed:               {len(failed)}")
    print()

    if demoted:
        print("Sample of demotions (first 5):")
        for v in demoted[:5]:
            print(f"  [{v['article_outlet']}] {v['article_title'][:80]}")
            print(f"    claim: {v['claim_text'][:100]}")
            print(f"    refutation found: {(v.get('refute_check_quote') or '')[:120]}")
            print()

    if not args.no_write:
        with open(args.input, "w") as f:
            json.dump(verdicts, f, indent=2)
        print(f"[write] {args.input}")
        print()
        print("Next: regenerate FINDINGS with the cleaned verdicts:")
        print("  python pipeline/stage5_report.py")
    else:
        print("[no-write] skipped writing back")


if __name__ == "__main__":
    main()
