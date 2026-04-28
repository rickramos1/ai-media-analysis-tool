"""Stage 1 of the cross-reference misinfo pipeline.

Classifies each article as FACT_CHECK, ORIGINAL, or OTHER. Inputs are eligible
rows from the preprocessed corpus. Output adds `article_type` and `classifier_reason`
columns. See docs/BACKLOG.md "Cross-reference misinfo detection" for the full spec.
"""
import csv
import os
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from dotenv import load_dotenv

from misinfo_detector import filter_eligible, format_hms

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_PARALLEL = int(os.environ.get("OLLAMA_PARALLEL", "4"))

csv.field_size_limit(2**30)

INPUT_CSV = "data/womens_health_articles_text_clean.csv"
OUTPUT_CSV = "data/articles_classified.csv"
VALID_TYPES = {"FACT_CHECK", "ORIGINAL", "OTHER"}

PROMPT_TEMPLATE = """/no_think
Classify this article into exactly one category based on its primary purpose:

- FACT_CHECK: The article's central purpose is to refute, debunk, or correct specific factual claims made by named sources. Typical structure: names a claim, presents evidence against it, cites experts/studies/regulators. Example: "Rep. X claimed Y, but the evidence shows Z."
- ORIGINAL: Reporting, opinion, or analysis that presents claims, events, or narratives as its own content, without structured refutation of named claims. Includes news stories, op-eds, advocacy pieces, and articles that promote claims.
- OTHER: Listicles, celebrity coverage, personal essays, wire-service roundups, or content not meaningfully engaging with factual claims about the topic.

Return ONLY a JSON object: {{"article_type": "FACT_CHECK" or "ORIGINAL" or "OTHER", "reason": "one-sentence justification"}}

ARTICLE TITLE: {title}
ARTICLE TEXT:
\"\"\"{text}\"\"\"
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


def classify(title, text, max_retries=3):
    prompt = PROMPT_TEMPLATE.format(title=title, text=text)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        # Ollama's native reasoning toggle. The `/no_think` prompt directive
        # is silently ignored by qwen3:14b; without `think: false` the model
        # burns the entire num_predict budget on a <think> block and returns
        # an empty response.
        "think": False,
        "options": {"temperature": 0, "num_predict": 500, "num_ctx": 8192},
    }).encode("utf-8")

    for _ in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = resp.read().decode("utf-8")
            parsed = _extract_json(json.loads(body).get("response", ""))
            if not parsed:
                continue
            atype = str(parsed.get("article_type", "")).strip().upper()
            if atype not in VALID_TYPES:
                continue
            return {
                "article_type": atype,
                "classifier_reason": str(parsed.get("reason", "")).strip(),
            }
        except Exception:
            continue
    return None


def run():
    df = pd.read_csv(INPUT_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    df = filter_eligible(df)
    eligible = df[df["eligible"]].copy()
    eligible["article_type"] = ""
    eligible["classifier_reason"] = ""

    if os.path.exists(OUTPUT_CSV):
        prev = pd.read_csv(OUTPUT_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
        done_map = {r["url"]: (r["article_type"], r["classifier_reason"])
                    for _, r in prev.iterrows()
                    if r.get("article_type") and r["article_type"] != "UNCLASSIFIED"}
        for idx, row in eligible.iterrows():
            if row["url"] in done_map:
                eligible.at[idx, "article_type"], eligible.at[idx, "classifier_reason"] = done_map[row["url"]]
        resumed = (eligible["article_type"] != "").sum()
        if resumed:
            print(f"[resume] found {resumed} rows already classified in {OUTPUT_CSV}")

    todo = eligible[eligible["article_type"] == ""]
    total = len(todo)
    print(f"[classify] {total} remaining, {OLLAMA_PARALLEL} workers")

    if total == 0:
        print("[OK] Nothing to do")
    else:
        start = time.time()

        def work(idx_row):
            idx, row = idx_row
            return idx, classify(row["title"], row["full_text"])

        with ThreadPoolExecutor(max_workers=OLLAMA_PARALLEL) as ex:
            futures = {ex.submit(work, ir): ir[0] for ir in todo.iterrows()}
            done = 0
            for fut in as_completed(futures):
                idx, result = fut.result()
                if result:
                    eligible.at[idx, "article_type"] = result["article_type"]
                    eligible.at[idx, "classifier_reason"] = result["classifier_reason"]
                else:
                    eligible.at[idx, "article_type"] = "UNCLASSIFIED"
                done += 1
                if done % 20 == 0 or done == total:
                    elapsed = time.time() - start
                    rate = done / elapsed if elapsed else 0
                    remaining = (total - done) / rate if rate else 0
                    eligible.to_csv(OUTPUT_CSV, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
                    print(f"  [{done}/{total}] elapsed {format_hms(elapsed)} | remaining {format_hms(remaining)} | {rate:.2f} rows/s [checkpoint]")

        eligible.to_csv(OUTPUT_CSV, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
        print(f"\n[OK] Classification complete in {format_hms(time.time()-start)} -> {OUTPUT_CSV}")

    print("\nDistribution by topic:")
    print(pd.crosstab(eligible["topic"], eligible["article_type"], margins=True))


if __name__ == "__main__":
    run()
