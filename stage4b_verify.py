"""Stage 4b of the cross-reference misinfo pipeline.

For each (article, claim) candidate pair from Stage 4a above a similarity
threshold, ask the LLM to classify how the article treats the claim:

- carrying: article presents the claim as true / endorses it
- debunking: article refutes the claim
- neutral_reporting: article says someone made the claim but doesn't endorse or refute
- irrelevant: article does not substantively discuss this claim

Output: stage4b_verdicts.json (per-pair verdicts) and misinfo_carriers.csv
(articles with ≥1 'carrying' verdict — the final misinfo detection result).
"""
import csv
import json
import os
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

CANDIDATES_JSON = "stage4a_candidates.json"
ARTICLES_CSV = "articles_classified.csv"
OUTPUT_JSON = "stage4b_verdicts.json"
CARRIERS_CSV = "misinfo_carriers.csv"
SIM_THRESHOLD = float(os.environ.get("STAGE4B_SIM", "0.68"))
VALID_VERDICTS = {"carrying", "debunking", "neutral_reporting", "irrelevant"}

PROMPT_TEMPLATE = """/no_think
You are determining how a news article handles a specific claim that has been previously debunked by fact-checkers.

CLAIM (previously debunked): "{claim_text}"
CLAIM ORIGINATOR: {claim_source}
HOW IT WAS DEBUNKED (per {fact_check_outlet}): {refutation}

Classify how the article below handles this claim.

Return ONLY a JSON object with these keys:
- "verdict": one of "carrying", "debunking", "neutral_reporting", "irrelevant"
- "evidence_quote": a direct quote or tight paraphrase from the article that supports your verdict, or null if the claim is not substantively addressed
- "reasoning": one sentence justifying the verdict

Definitions:
- "carrying" = the article presents the claim as true, endorses it, or repeats it uncritically in a way that could lead a reader to accept it as fact.
- "debunking" = the article explicitly refutes the claim, citing counter-evidence, experts, or regulators.
- "neutral_reporting" = the article mentions the claim (e.g. "X said Y") without endorsing or refuting it; purely descriptive.
- "irrelevant" = the article does not substantively discuss this specific claim; the topic overlap is incidental.

Be strict. Do not classify an article as "carrying" if it merely quotes the claim while framing it as disputed, contested, or coming from a partisan source.

ARTICLE TITLE: {article_title}
ARTICLE SOURCE: {article_outlet}
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


def verify(claim, article_title, article_outlet, article_text, max_retries=3):
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
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
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
        except Exception:
            continue
    return None


def pair_key(article_url, claim_id):
    return f"{article_url}||{claim_id}"


def run():
    with open(CANDIDATES_JSON) as f:
        cand = json.load(f)

    claims_by_id = {c["claim_id"]: c for c in cand["claims"]}

    # Build list of (article, claim) pairs above threshold
    articles_df = pd.read_csv(ARTICLES_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    articles_by_url = {r["url"]: r for _, r in articles_df.iterrows()}

    pairs = []
    for art in cand["per_article"]:
        for m in art["top_matches"]:
            if m["similarity"] >= SIM_THRESHOLD:
                pairs.append({
                    "article_url": art["article_url"],
                    "article_title": art["article_title"],
                    "article_outlet": art["article_outlet"],
                    "article_topic": art["article_topic"],
                    "claim_id": m["claim_id"],
                    "similarity": m["similarity"],
                })

    print(f"[stage4b] {len(pairs)} pairs above sim >= {SIM_THRESHOLD}")

    # Load existing checkpoint if any
    done_keys = set()
    results = []
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON) as f:
            results = json.load(f)
        done_keys = {pair_key(r["article_url"], r["claim_id"]) for r in results}
        print(f"[resume] {len(done_keys)} pairs already done")

    todo = [p for p in pairs if pair_key(p["article_url"], p["claim_id"]) not in done_keys]
    total = len(todo)
    print(f"[stage4b] {total} pairs remaining, {OLLAMA_PARALLEL} workers")

    if total == 0:
        print("[OK] Nothing to do")
    else:
        start = time.time()

        def work(pair):
            claim = claims_by_id[pair["claim_id"]]
            article = articles_by_url.get(pair["article_url"])
            if article is None:
                return None
            result = verify(
                claim=claim,
                article_title=article["title"],
                article_outlet=article["media_name"],
                article_text=article["full_text"],
            )
            out = {**pair, **(result or {"verdict": "UNKNOWN", "evidence_quote": None, "reasoning": ""})}
            out["claim_text"] = claim["claim_text"]
            out["claim_source"] = claim["claim_source"]
            out["fact_check_outlet"] = claim["fact_check_outlet"]
            out["fact_check_url"] = claim["fact_check_url"]
            return out

        with ThreadPoolExecutor(max_workers=OLLAMA_PARALLEL) as ex:
            futures = [ex.submit(work, p) for p in todo]
            done = 0
            for fut in as_completed(futures):
                r = fut.result()
                if r:
                    results.append(r)
                done += 1
                if done % 10 == 0 or done == total:
                    elapsed = time.time() - start
                    rate = done / elapsed if elapsed else 0
                    remaining = (total - done) / rate if rate else 0
                    with open(OUTPUT_JSON, "w") as f:
                        json.dump(results, f, indent=2)
                    print(f"  [{done}/{total}] elapsed {format_hms(elapsed)} | remaining {format_hms(remaining)} | {rate:.2f} pairs/s [checkpoint]")

        with open(OUTPUT_JSON, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n[OK] Verification complete in {format_hms(time.time()-start)} -> {OUTPUT_JSON}")

    # Build misinfo carriers CSV: one row per carrying verdict
    carriers = [r for r in results if r.get("verdict") == "carrying"]
    if carriers:
        car_df = pd.DataFrame(carriers)
        car_df = car_df[["article_url", "article_title", "article_outlet", "article_topic",
                         "similarity", "claim_text", "claim_source", "fact_check_outlet",
                         "fact_check_url", "evidence_quote", "reasoning"]]
        car_df.to_csv(CARRIERS_CSV, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
        print(f"[write] {CARRIERS_CSV}: {len(carriers)} carrying verdicts "
              f"across {car_df['article_url'].nunique()} unique articles")

    # Report
    from collections import Counter
    verdict_counts = Counter(r.get("verdict", "MISSING") for r in results)
    print("\nVerdict distribution:")
    for v, n in verdict_counts.most_common():
        print(f"  {v:20s} {n}")


if __name__ == "__main__":
    run()
