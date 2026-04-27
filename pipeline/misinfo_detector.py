import csv
import os
import pandas as pd
import json
import time
import re
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_PARALLEL = int(os.environ.get("OLLAMA_PARALLEL", "2"))
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "180"))

csv.field_size_limit(2**30)

INPUT_RAW = "data/womens_health_articles_text.csv"
INPUT_CLEANED = "data/womens_health_articles_text_clean.csv"
BAD_ROWS = "data/bad_rows.csv"
OUTPUT_CSV = "data/misinfo_flagged_output.csv"
SCORES_CSV = "data/article_topic_scores.csv"
DEDUP_CSV = "data/article_dedup_map.csv"
SEMANTIC_GATE_THRESHOLD = float(os.environ.get("SEMANTIC_GATE_THRESHOLD", "0.70"))

# Topic relevance: per-topic vocabulary that must appear at least once. Terms
# are clinical/regulatory only — no editorial loading like "misinformation".
TOPIC_TERMS = {
    # Original fact-check-focused topics (kept for backward compatibility).
    "birth control myths": [
        r"birth control", r"contracepti(on|ve|ves)", r"the pill\b", r"\bIUDs?\b",
        r"intrauterine", r"Depo[- ]?Provera", r"Nexplanon", r"hormonal birth",
        r"oral contraceptive", r"contraceptive pill",
    ],
    "emergency contraception": [
        r"emergency contracepti(on|ve)", r"Plan B\b", r"morning[- ]after pill",
        r"\bElla\b(?! ?Fitzgerald)", r"ulipristal", r"levonorgestrel",
    ],
    "mifepristone misinformation": [
        r"mifepristone", r"abortion pill", r"Mifeprex", r"RU[- ]?486",
        r"medication abortion", r"misoprostol",
    ],
    "pregnancy crisis centers": [
        r"crisis pregnancy center", r"pregnancy crisis center",
        r"pregnancy resource center", r"\bCPCs?\b", r"anti[- ]abortion center",
        r"pregnancy help center",
    ],
    # Carrier-focused topics (matching queries_public_collection_womens_health.py).
    "abortion pill reversal": [
        r"abortion pill reversal", r"\bAPR\b", r"mifepristone reversal",
        r"mifepristone", r"abortion pill",
    ],
    "chemical abortion harms": [
        r"chemical abortion", r"mifepristone", r"abortion pill", r"misoprostol",
        r"medication abortion",
    ],
    "emergency contraception abortifacient": [
        r"Plan B\b", r"emergency contracepti(on|ve)", r"morning[- ]after pill",
        r"\bElla\b(?! ?Fitzgerald)", r"ulipristal", r"levonorgestrel",
    ],
    "birth control harm claims": [
        r"birth control", r"the pill\b", r"hormonal contracepti(on|ve)",
        r"oral contracepti(on|ve)", r"contracepti(on|ve|ves)",
    ],
    "IUD misinfo": [
        r"\bIUDs?\b", r"intrauterine", r"Mirena", r"Paragard", r"Skyla",
        r"Liletta", r"Kyleena", r"Nexplanon",
    ],
    "mifepristone safety attack": [
        r"mifepristone", r"abortion pill", r"Mifeprex", r"RU[- ]?486",
        r"medication abortion", r"misoprostol", r"\bREMS\b",
    ],
    "fertility awareness superiority": [
        r"fertility awareness", r"natural family planning", r"\bNFP\b",
        r"cycle tracking", r"\bFAM\b", r"Creighton model", r"rhythm method",
    ],
    "CPC promotion": [
        r"crisis pregnancy center", r"pregnancy resource center",
        r"pregnancy help center", r"\bCPCs?\b", r"pregnancy care center",
    ],
    "trad wife anti-contraception": [
        r"trad wife", r"traditional wife", r"homeschool", r"birth control",
        r"contracepti(on|ve|ves)", r"natural cycle", r"fertility",
    ],
    "wellness hormone influencers": [
        r"hormonal? imbalance", r"\bhormones?\b", r"seed cycling", r"cortisol",
        r"menstrua", r"fertility", r"women.s health", r"women'?s health",
    ],
}
TOPIC_RX = {t: re.compile("|".join(terms), re.IGNORECASE) for t, terms in TOPIC_TERMS.items()}

# Medical/policy/health context vocabulary. Article must contain at least one
# topic term AND at least one context term to be considered on-topic.
# Drops cases like "wild horse birth control" or "Plan B" used as idiom.
CONTEXT_RX = re.compile(
    r"\b(FDA|CDC|HHS|Medicaid|Medicare|prescription|prescribe|physician|doctor|nurse|"
    r"clinic|clinical|hospital|patient|patients|study|studies|trial|trials|research|"
    r"researcher|legislation|legislator|senator|senate|congress|bill|law|court|"
    r"ruling|judge|regulator|regulation|dose|dosage|side effect|side[- ]effects|"
    r"pregnancy|pregnant|reproductive|gynecolog|obstetric|OB[- ]?GYN|fertility|"
    r"hormone|estrogen|progest|abortion|miscarriage|womens? health|women.s health|"
    r"insurance|premium|coverage|public health|epidemiolog)\b",
    re.IGNORECASE,
)


def preprocess_csv(input_path, cleaned_path, bad_path):
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False, on_bad_lines="skip")
    expected_cols = df.columns.tolist()
    df["__col_count"] = df.apply(lambda r: len(r), axis=1)
    good_df = df[df["__col_count"] == len(expected_cols)].drop(columns="__col_count")
    bad_df = df[df["__col_count"] != len(expected_cols)].drop(columns="__col_count")
    good_df.to_csv(cleaned_path, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
    bad_df.to_csv(bad_path, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
    print(f"[OK] Preprocessing: {len(good_df)} good rows, {len(bad_df)} bad rows")


def is_on_topic(topic, body):
    rx = TOPIC_RX.get(topic)
    if not rx:
        return False
    return bool(rx.search(body)) and bool(CONTEXT_RX.search(body))


PROMPT_TEMPLATE = """/no_think
You are a careful fact-checking assistant analyzing a news article on women's health. The topic this article was retrieved under is: "{topic}".

Return ONLY a JSON object with these exact keys:
- "summary": 2-3 sentence neutral summary of the article's central claims (no editorializing, no fact-check verdict).
- "on_topic": boolean. True if the article substantively discusses the topic above; False if it only mentions the topic in passing or is unrelated.
- "misleading": one of "True", "False", or "Unknown". Use "Unknown" when you lack the evidence to decide — do NOT guess.
- "reason": 1-2 sentence justification for the misleading verdict, citing specific claims when possible.

Do not include any text outside the JSON. Do not invent facts not present in the article.

ARTICLE:
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


def call_llm(topic, text, max_retries=3):
    prompt = PROMPT_TEMPLATE.format(topic=topic, text=text)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 800,
        },
    }).encode("utf-8")

    for _ in range(max_retries):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
            response = json.loads(body).get("response", "").strip()
            parsed = _extract_json(response)
            if not parsed:
                continue
            verdict = str(parsed.get("misleading", "")).strip().capitalize()
            if verdict not in ("True", "False", "Unknown"):
                continue
            return {
                "summary": str(parsed.get("summary", "")).strip(),
                "on_topic_llm": bool(parsed.get("on_topic", True)),
                "misleading": verdict,
                "reason": str(parsed.get("reason", "")).strip(),
            }
        except Exception:
            continue
    return None


def format_hms(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"


def _load_semantic_score_map(path):
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    if "url" not in df.columns or "semantic_topic_score" not in df.columns:
        return {}
    scores = pd.to_numeric(df["semantic_topic_score"], errors="coerce")
    return dict(zip(df["url"], scores))


def _load_non_canonical_keys(path):
    """Return set of (url, topic) tuples flagged is_canonical=False.

    The dedup map is keyed on (url, article_topic) because the same URL caught
    by multiple topic queries is canonicalized to ONE topic and dropped from
    the others (URL-collision pass). Joining on url alone would drop the
    canonical instance too.
    """
    if not os.path.exists(path):
        return set()
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    if not {"url", "is_canonical", "article_topic"}.issubset(df.columns):
        return set()
    is_canon = df["is_canonical"].astype(str).str.lower().isin(["true", "1"])
    return set(zip(df.loc[~is_canon, "url"], df.loc[~is_canon, "article_topic"]))


def filter_eligible(df, *, hybrid=True, semantic_threshold=SEMANTIC_GATE_THRESHOLD,
                    scores_path=SCORES_CSV, dedup_path=DEDUP_CSV):
    """Filter to eligible articles for downstream LLM stages.

    Eligibility = passes_wc AND (passes_topic_gate OR passes_semantic_gate) AND is_canonical.

    `hybrid=False` returns the legacy regex-only behavior; useful for shadow
    comparisons (e.g. semantic_topic_gate.py's calibration report).
    """
    df = df.copy()
    df["wc"] = df["full_text"].str.split().str.len().fillna(0).astype(int)
    df["passes_wc"] = df["wc"] >= 100
    df["passes_topic_gate"] = df.apply(
        lambda r: is_on_topic(r["topic"], r["full_text"]), axis=1
    )

    if hybrid:
        score_map = _load_semantic_score_map(scores_path)
        if score_map:
            df["semantic_topic_score"] = df["url"].map(score_map)
            df["passes_semantic_gate"] = (df["semantic_topic_score"] >= semantic_threshold).fillna(False)
        else:
            df["semantic_topic_score"] = float("nan")
            df["passes_semantic_gate"] = False

        non_canonical = _load_non_canonical_keys(dedup_path)
        if non_canonical:
            keys = list(zip(df["url"], df["topic"]))
            df["is_canonical"] = [k not in non_canonical for k in keys]
        else:
            df["is_canonical"] = True
    else:
        df["semantic_topic_score"] = float("nan")
        df["passes_semantic_gate"] = False
        df["is_canonical"] = True

    df["eligible"] = (
        df["passes_wc"]
        & (df["passes_topic_gate"] | df["passes_semantic_gate"])
        & df["is_canonical"]
    )

    sem_only_admit = int(((~df["passes_topic_gate"]) & df["passes_semantic_gate"]
                          & df["passes_wc"] & df["is_canonical"]).sum())
    dedup_drops = int((~df["is_canonical"]).sum()) if hybrid else 0
    sem_n = int(df["passes_semantic_gate"].sum())
    print(
        f"[gate] {df.passes_wc.sum()} pass wc | "
        f"{df.passes_topic_gate.sum()} pass regex topic+context | "
        f"{sem_n} pass semantic (>= {semantic_threshold:.2f}) | "
        f"+{sem_only_admit} admitted via semantic only | "
        f"-{dedup_drops} dropped as non-canonical | "
        f"{df.eligible.sum()} eligible for LLM"
    )
    return df


def run_analysis(input_file, output_file, max_rows=None):
    df = pd.read_csv(input_file, dtype=str, keep_default_na=False, encoding="utf-8")
    df = filter_eligible(df)
    eligible = df[df["eligible"]].copy()
    if max_rows:
        eligible = eligible.head(max_rows)

    total = len(eligible)
    print(f"[run] Processing {total} eligible articles with {OLLAMA_PARALLEL} parallel workers")
    start = time.time()
    results = {}

    def work(idx_row):
        idx, row = idx_row
        return idx, call_llm(row["topic"], row["full_text"])

    with ThreadPoolExecutor(max_workers=OLLAMA_PARALLEL) as ex:
        futures = {ex.submit(work, ir): ir[0] for ir in eligible.iterrows()}
        done = 0
        for fut in as_completed(futures):
            idx, result = fut.result()
            results[idx] = result
            done += 1
            if done % 10 == 0 or done == total:
                elapsed = time.time() - start
                rate = done / elapsed if elapsed else 0
                remaining = (total - done) / rate if rate else 0
                print(
                    f"  [{done}/{total}] elapsed {format_hms(elapsed)} | "
                    f"remaining {format_hms(remaining)} | {rate:.2f} rows/s"
                )

    out_rows = []
    for idx, row in eligible.iterrows():
        r = results.get(idx)
        if not r:
            continue
        row["summary"] = r["summary"]
        row["misleading"] = r["misleading"]
        row["reason"] = r["reason"]
        row["on_topic_llm"] = "True" if r["on_topic_llm"] else "False"
        out_rows.append(row)

    out_df = pd.DataFrame(out_rows)
    out_df.to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
    elapsed = time.time() - start
    print(f"[OK] Analysis complete in {format_hms(elapsed)}. {len(out_df)} rows -> {output_file}")
    if len(out_df):
        print(f"     verdicts: " + ", ".join(
            f"{v}={int((out_df['misleading']==v).sum())}"
            for v in ("True", "False", "Unknown")
        ))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rows", type=int, default=None, help="Limit number of rows (smoke test)")
    parser.add_argument("--skip-preprocess", action="store_true", help="Skip CSV preprocessing step")
    args = parser.parse_args()

    if not args.skip_preprocess:
        preprocess_csv(INPUT_RAW, INPUT_CLEANED, BAD_ROWS)
    run_analysis(INPUT_CLEANED, OUTPUT_CSV, max_rows=args.max_rows)
