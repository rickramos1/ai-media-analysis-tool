"""Semantic topic gate (shadow mode).

Computes a per-article topic-similarity score using nomic-embed-text and
compares it against the current regex-based `passes_topic_gate` from
`misinfo_detector.filter_eligible`. Writes a comparison report so we can
calibrate a threshold before replacing the regex gate.

Inputs:
- `womens_health_articles_text_clean.csv` — all scraped articles (pre-gate)
- `articles_classified.csv` — supplies seed articles (top-K per topic that
  passed the regex gate AND were classified ORIGINAL or FACT_CHECK)
- `queries_public_collection_womens_health.TOPIC_QUERIES` — query strings

Outputs:
- `article_topic_scores.csv` — url, topic, regex_passes_topic_gate,
  semantic_topic_score (one row per clean article)
- `article_topic_embeddings.npy` + manifest — article embeddings (reusable)
- `topic_centroids.npy` + manifest — per-topic centroid vectors
- Stdout calibration report: score distributions + agreement/disagreement
  counts vs the regex gate at candidate thresholds
"""
import json
import os
import re
import time
import urllib.request
from collections import defaultdict

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from misinfo_detector import filter_eligible, is_on_topic
from queries_public_collection_womens_health import TOPIC_QUERIES

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

CLEAN_CSV = "data/womens_health_articles_text_clean.csv"
CLASSIFIED_CSV = "data/articles_classified.csv"
SCORES_CSV = "data/article_topic_scores.csv"
ARTICLE_EMB_NPY = "data/article_topic_embeddings.npy"
ARTICLE_EMB_MANIFEST = "data/article_topic_embeddings_manifest.json"
CENTROID_NPY = "data/topic_centroids.npy"
CENTROID_MANIFEST = "data/topic_centroids_manifest.json"

LEAD_WORDS = 400
SEEDS_PER_TOPIC = 10
MAX_EMBED_WORDS = 1500

CANDIDATE_THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]


def _truncate_for_embed(s):
    words = s.split()
    return " ".join(words[:MAX_EMBED_WORDS]) if len(words) > MAX_EMBED_WORDS else s


def _embed_call(texts):
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)["embeddings"]


def embed_batch(texts, batch_size=16, label=""):
    if not texts:
        return np.zeros((0, 768), dtype=np.float32)
    dim = None
    vectors = [None] * len(texts)
    texts = [_truncate_for_embed(t) for t in texts]
    start = time.time()
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            embs = _embed_call(batch)
            for j, e in enumerate(embs):
                vectors[i + j] = e
                if dim is None:
                    dim = len(e)
        except Exception as exc:
            print(f"  [embed] batch failed ({exc}); single-item fallback")
            for j, t in enumerate(batch):
                try:
                    vectors[i + j] = _embed_call([t])[0]
                    if dim is None:
                        dim = len(vectors[i + j])
                except Exception:
                    vectors[i + j] = None
        done = min(i + batch_size, len(texts))
        if done % (batch_size * 4) == 0 or done == len(texts):
            elapsed = time.time() - start
            rate = done / elapsed if elapsed else 0
            print(f"  [embed:{label}] {done}/{len(texts)} | {rate:.1f} texts/s")
    if dim is None:
        dim = 768
    arr = np.zeros((len(texts), dim), dtype=np.float32)
    for i, v in enumerate(vectors):
        if v is not None:
            arr[i] = np.asarray(v, dtype=np.float32)
    return arr


def article_input_text(title, body):
    """Concatenate title + first LEAD_WORDS words of body."""
    title = (title or "").strip()
    body_words = (body or "").split()
    lead = " ".join(body_words[:LEAD_WORDS])
    return f"{title}\n\n{lead}".strip()


def cosine(a, b):
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def clean_query_text(q):
    """Strip boolean operators so embedding sees the lexical content."""
    q = re.sub(r"\b(AND NOT|AND|OR|NOT)\b", " ", q)
    q = re.sub(r'[()"]+', " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def pick_seeds(classified_df, per_topic):
    """For each topic, pick up to `per_topic` eligible ORIGINAL/FACT_CHECK articles."""
    eligible_types = {"ORIGINAL", "FACT_CHECK"}
    df = classified_df[classified_df["article_type"].isin(eligible_types)]
    seeds_by_topic = {}
    for topic, sub in df.groupby("topic"):
        sub = sub.sort_values("wc", ascending=False, key=lambda s: s.astype(int))
        seeds_by_topic[topic] = sub.head(per_topic)[["url", "title", "full_text"]].to_dict("records")
    return seeds_by_topic


def build_centroids(seeds_by_topic):
    """For each topic: centroid = mean of (label+query embedding, each seed embedding)."""
    topics = list(TOPIC_QUERIES.keys())
    # First, embed the topic label + query text for each topic.
    label_inputs = [f"{t}. {clean_query_text(q)}" for t, q in TOPIC_QUERIES.items()]
    print(f"[centroids] embedding {len(label_inputs)} topic label+query texts")
    label_vecs = embed_batch(label_inputs, label="labels")

    # Then embed all seed articles in one batch (keeping topic assignment).
    seed_inputs = []
    seed_topic_of = []
    for topic in topics:
        for s in seeds_by_topic.get(topic, []):
            seed_inputs.append(article_input_text(s["title"], s["full_text"]))
            seed_topic_of.append(topic)
    print(f"[centroids] embedding {len(seed_inputs)} seed articles across {len(topics)} topics")
    seed_vecs = embed_batch(seed_inputs, label="seeds") if seed_inputs else np.zeros((0, label_vecs.shape[1]), dtype=np.float32)

    # Combine per topic.
    dim = label_vecs.shape[1]
    centroids = np.zeros((len(topics), dim), dtype=np.float32)
    manifest = []
    for ti, topic in enumerate(topics):
        vectors = [label_vecs[ti]]
        seed_idxs = [i for i, t in enumerate(seed_topic_of) if t == topic]
        for idx in seed_idxs:
            vectors.append(seed_vecs[idx])
        centroids[ti] = np.mean(vectors, axis=0)
        manifest.append({
            "topic": topic,
            "centroid_idx": ti,
            "n_seeds": len(seed_idxs),
            "source": "topic_label + query_text + seed_articles",
        })
    return centroids, topics, manifest


def run():
    print(f"[config] OLLAMA_HOST={OLLAMA_HOST} EMBED_MODEL={EMBED_MODEL}")

    # 1. Load all scraped articles (pre-gate)
    df_clean = pd.read_csv(CLEAN_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    print(f"[load] {CLEAN_CSV}: {len(df_clean)} rows")

    # 2. Apply regex gate so we have the comparison column. Pass hybrid=False
    #    so this script's shadow report stays a clean regex-vs-semantic compare,
    #    independent of any prior scores/dedup map on disk.
    gated = filter_eligible(df_clean.copy(), hybrid=False)

    # 3. Build seed set from prior classifier output.
    if os.path.exists(CLASSIFIED_CSV):
        df_class = pd.read_csv(CLASSIFIED_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
        seeds_by_topic = pick_seeds(df_class, SEEDS_PER_TOPIC)
        total_seeds = sum(len(v) for v in seeds_by_topic.values())
        print(f"[seeds] drew {total_seeds} seed articles from {CLASSIFIED_CSV}")
    else:
        print(f"[seeds] {CLASSIFIED_CSV} missing — centroids will use query text only")
        seeds_by_topic = {}

    # 4. Build centroids.
    centroids, topic_order, centroid_manifest = build_centroids(seeds_by_topic)
    np.save(CENTROID_NPY, centroids)
    with open(CENTROID_MANIFEST, "w") as f:
        json.dump({"model": EMBED_MODEL, "dim": int(centroids.shape[1]), "topics": centroid_manifest}, f, indent=2)
    topic_to_idx = {t: i for i, t in enumerate(topic_order)}
    print(f"[centroids] {centroids.shape} written to {CENTROID_NPY}")

    # 5. Embed every article (title + lead).
    inputs = [article_input_text(r["title"], r["full_text"]) for _, r in gated.iterrows()]
    print(f"[articles] embedding {len(inputs)} articles (title + first {LEAD_WORDS} words)")
    article_vecs = embed_batch(inputs, label="articles")
    np.save(ARTICLE_EMB_NPY, article_vecs)
    emb_manifest = {
        "model": EMBED_MODEL,
        "dim": int(article_vecs.shape[1]),
        "lead_words": LEAD_WORDS,
        "articles": [
            {
                "article_idx": i,
                "url": r["url"],
                "topic": r["topic"],
                "wc": int(r["wc"]) if r.get("wc") not in (None, "") else None,
            }
            for i, (_, r) in enumerate(gated.iterrows())
        ],
    }
    with open(ARTICLE_EMB_MANIFEST, "w") as f:
        json.dump(emb_manifest, f, indent=2)
    print(f"[articles] {article_vecs.shape} written to {ARTICLE_EMB_NPY}")

    # 6. Score each article against its topic's centroid.
    scores = np.zeros(len(gated), dtype=np.float32)
    unknown_topics = set()
    for i, topic in enumerate(gated["topic"].tolist()):
        ci = topic_to_idx.get(topic)
        if ci is None:
            unknown_topics.add(topic)
            scores[i] = np.nan
            continue
        scores[i] = cosine(article_vecs[i], centroids[ci])
    if unknown_topics:
        print(f"[warn] {len(unknown_topics)} unknown topics not in TOPIC_QUERIES: {sorted(unknown_topics)}")

    gated_out = gated[["url", "topic", "wc", "passes_wc", "passes_topic_gate"]].copy()
    gated_out["semantic_topic_score"] = scores
    gated_out.to_csv(SCORES_CSV, index=False, encoding="utf-8")
    print(f"[write] {SCORES_CSV}: {len(gated_out)} rows")

    # 7. Calibration report.
    print_calibration_report(gated_out)


def print_calibration_report(df):
    print("\n" + "=" * 60)
    print("CALIBRATION REPORT")
    print("=" * 60)

    scored = df.dropna(subset=["semantic_topic_score"]).copy()
    scored["semantic_topic_score"] = scored["semantic_topic_score"].astype(float)
    scored["passes_topic_gate"] = scored["passes_topic_gate"].astype(bool) if scored["passes_topic_gate"].dtype != bool else scored["passes_topic_gate"]
    # pandas writes bools as strings in our csv pipeline; guard for that.
    if scored["passes_topic_gate"].dtype == object:
        scored["passes_topic_gate"] = scored["passes_topic_gate"].astype(str).str.lower().isin(["true", "1"])

    print(f"\nArticles scored: {len(scored)} / {len(df)}")

    print("\nPer-topic score stats (semantic):")
    print(f"  {'topic':<40s} {'n':>5s} {'mean':>6s} {'p10':>6s} {'p50':>6s} {'p90':>6s}")
    for topic, sub in scored.groupby("topic"):
        s = sub["semantic_topic_score"]
        print(f"  {topic:<40s} {len(sub):>5d} {s.mean():>6.3f} {s.quantile(0.10):>6.3f} {s.quantile(0.50):>6.3f} {s.quantile(0.90):>6.3f}")

    print("\nAgreement with regex gate at candidate thresholds:")
    print(f"  {'thr':>5s}  {'both_pass':>10s} {'both_drop':>10s} {'regex_only':>11s} {'sem_only':>10s} {'f1_vs_regex':>12s}")
    for thr in CANDIDATE_THRESHOLDS:
        sem_pass = scored["semantic_topic_score"] >= thr
        reg_pass = scored["passes_topic_gate"]
        both_pass = int((sem_pass & reg_pass).sum())
        both_drop = int((~sem_pass & ~reg_pass).sum())
        regex_only = int((~sem_pass & reg_pass).sum())   # regex passes, sem drops
        sem_only = int((sem_pass & ~reg_pass).sum())     # sem passes, regex drops
        # F1 treating regex gate as reference label
        tp = both_pass
        fp = sem_only
        fn = regex_only
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        print(f"  {thr:>5.2f}  {both_pass:>10d} {both_drop:>10d} {regex_only:>11d} {sem_only:>10d} {f1:>12.3f}")
    print("\nNotes:")
    print("- regex_only = article regex gate passed but semantic score is low → would be newly dropped")
    print("- sem_only   = article regex gate failed but semantic score is high → would be newly admitted")
    print("- 'F1 vs regex' treats the regex gate as labels; look at regex_only / sem_only absolute counts too,")
    print("  since the whole point is to disagree with regex where regex is wrong.")


if __name__ == "__main__":
    run()
