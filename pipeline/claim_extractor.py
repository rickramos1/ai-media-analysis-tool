"""Stage 2 of the cross-reference misinfo pipeline.

For each FACT_CHECK article (as classified by article_classifier.py), extract
structured debunked claims: what was claimed, who claimed it, how the article
refutes it, and what evidence is cited. Output is a JSON array of article
objects, each with a list of claims. See docs/BACKLOG.md for the full architecture.
"""
import csv
import os
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from dotenv import load_dotenv

from misinfo_detector import format_hms

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_PARALLEL = int(os.environ.get("OLLAMA_PARALLEL", "4"))

csv.field_size_limit(2**30)

INPUT_CSV = "data/articles_classified.csv"
OUTPUT_JSON = "data/claims.json"

PROMPT_TEMPLATE = """/no_think
You are extracting claims from a fact-checking article. Identify claims the article REFUTES or DEBUNKS — not claims the article itself is making.

For each debunked claim, extract:
- "claim_text": the specific statement being refuted (quote or tight paraphrase)
- "claim_source": who made the claim (person, outlet, organization) if named, else null
- "refutation": what evidence or authority the article cites to refute it (1-2 sentences)
- "evidence_sources": list of studies, experts, institutions, or documents cited as evidence against the claim

Return ONLY a JSON object: {{"claims": [ {{claim_text, claim_source, refutation, evidence_sources}}, ... ]}}

If the article does not debunk any specific claim, return {{"claims": []}}. Do not include any text outside the JSON. Do not invent facts not present in the article.

ARTICLE TITLE: {title}
ARTICLE SOURCE: {source}
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


def extract_claims(title, source, text, max_retries=3):
    prompt = PROMPT_TEMPLATE.format(title=title, source=source, text=text)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        # Ollama's native reasoning toggle. The `/no_think` prompt directive
        # is silently ignored by qwen3:14b; without `think: false` the model
        # burns the entire num_predict budget on a <think> block and returns
        # an empty response.
        "think": False,
        "options": {"temperature": 0, "num_predict": 1500, "num_ctx": 8192},
    }).encode("utf-8")

    for _ in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = resp.read().decode("utf-8")
            parsed = _extract_json(json.loads(body).get("response", ""))
            if parsed and isinstance(parsed.get("claims"), list):
                return parsed["claims"]
        except Exception:
            continue
    return None


def run():
    df = pd.read_csv(INPUT_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    fact_checks = df[df["article_type"] == "FACT_CHECK"].copy()
    print(f"[extract] {len(fact_checks)} FACT_CHECK articles in {INPUT_CSV}")

    existing = []
    done_urls = set()
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON) as f:
            existing = json.load(f)
        done_urls = {a["article_url"] for a in existing}
        print(f"[resume] {len(done_urls)} already extracted in {OUTPUT_JSON}")

    todo = fact_checks[~fact_checks["url"].isin(done_urls)]
    total = len(todo)
    print(f"[extract] {total} remaining, {OLLAMA_PARALLEL} workers")

    if total == 0:
        print("[OK] Nothing to do")
    else:
        start = time.time()
        results = list(existing)

        def work(row):
            claims = extract_claims(row["title"], row["media_name"], row["full_text"])
            return {
                "article_url": row["url"],
                "article_title": row["title"],
                "fact_check_outlet": row["media_name"],
                "topic": row["topic"],
                "publish_date": row.get("publish_date", ""),
                "claims": claims if claims is not None else [],
                "extraction_failed": claims is None,
            }

        with ThreadPoolExecutor(max_workers=OLLAMA_PARALLEL) as ex:
            futures = [ex.submit(work, r) for _, r in todo.iterrows()]
            done = 0
            for fut in as_completed(futures):
                results.append(fut.result())
                done += 1
                if done % 5 == 0 or done == total:
                    elapsed = time.time() - start
                    rate = done / elapsed if elapsed else 0
                    remaining = (total - done) / rate if rate else 0
                    with open(OUTPUT_JSON, "w") as f:
                        json.dump(results, f, indent=2)
                    print(f"  [{done}/{total}] elapsed {format_hms(elapsed)} | remaining {format_hms(remaining)} | {rate:.2f} rows/s [checkpoint]")

        with open(OUTPUT_JSON, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n[OK] Extraction complete in {format_hms(time.time()-start)} -> {OUTPUT_JSON}")

    with open(OUTPUT_JSON) as f:
        final = json.load(f)
    total_claims = sum(len(a["claims"]) for a in final)
    failed = sum(1 for a in final if a.get("extraction_failed"))
    print(f"\n{len(final)} articles, {total_claims} total claims, {failed} extraction failures")


if __name__ == "__main__":
    run()
