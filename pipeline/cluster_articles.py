"""Emergent-narrative topic clustering.

Clusters article embeddings independent of MediaCloud query labels to
surface narratives, outlet networks, or topic bleed the query design
missed.

Pipeline:
1. Load embeddings from `article_topic_embeddings.npy`.
2. Drop non-canonical dedupe members so syndicates don't dominate clusters.
3. Agglomerative cluster via union-find at cosine >= SIM_THRESHOLD.
4. For each cluster (size >= MIN_CLUSTER_SIZE): pick the most-central
   article, compute outlet/topic distributions, and extract
   distinguishing n-grams (cluster-frequency / corpus-frequency).
5. Emit:
   - `article_clusters.csv` — per-article cluster assignment
   - `docs/narrative_clusters.md` — human-readable cluster summaries

Shadow mode — not wired into the pipeline.
"""
import json
import os
import re
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

EMB_NPY = "data/article_topic_embeddings.npy"
EMB_MANIFEST = "data/article_topic_embeddings_manifest.json"
DEDUP_CSV = "data/article_dedup_map.csv"
CLEAN_CSV = "data/womens_health_articles_text_clean.csv"
OUT_CSV = "data/article_clusters.csv"
OUT_MD = "docs/narrative_clusters.md"

SIM_THRESHOLD = 0.88
MIN_CLUSTER_SIZE = 3
NGRAM_RANGE = (1, 3)
TOP_NGRAMS_PER_CLUSTER = 10
TOP_ARTICLES_PER_CLUSTER = 5
MIN_CORPUS_FREQ = 3          # ignore n-grams that appear fewer times across corpus
MIN_NGRAM_CHARS = 4          # drop 1-2 char tokens
TOP_OUTLETS_PER_CLUSTER = 5

# Small English + domain-noise stopword set. Keep legible narratives by
# dropping content-free tokens AND the near-universal women's-health
# vocabulary that appears in every cluster.
STOPWORDS = set("""
a about above after again against all am an and any are as at be because been before being below between
both but by could did do does doing don down during each few for from further had has have having he her
here hers herself him himself his how i if in into is it its itself just me more most my myself no nor
not now of off on once only or other our ours ourselves out over own same she should so some such than
that the their theirs them themselves then there these they this those through to too under until up
very was we were what when where which while who whom why will with you your yours yourself yourselves
would should could may might must can cannot s t re ve ll d ve m o re new news says said say like get got
also first last one two three said says new news
""".split())

DOMAIN_COMMON = set("""
women woman female abortion pregnancy pregnant fetus fetal birth fertility reproductive health medical
care patient patients doctor doctors nurse clinic clinical hospital drug drugs pill pills
""".split())

STOPWORDS |= DOMAIN_COMMON


class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def tokenize(text):
    tokens = re.findall(r"[a-z][a-z\-']+", (text or "").lower())
    return [t for t in tokens if len(t) >= MIN_NGRAM_CHARS and t not in STOPWORDS]


def ngrams(tokens, n_min, n_max):
    out = []
    for n in range(n_min, n_max + 1):
        for i in range(len(tokens) - n + 1):
            out.append(" ".join(tokens[i:i + n]))
    return out


def load():
    vecs = np.load(EMB_NPY)
    with open(EMB_MANIFEST) as f:
        manifest = json.load(f)
    rows = [
        {
            "idx": a["article_idx"],
            "url": a["url"],
            "topic": a["topic"],
            "wc": a.get("wc") or 0,
        }
        for a in manifest["articles"]
    ]

    clean = pd.read_csv(CLEAN_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    clean_by_url = {r["url"]: r for _, r in clean.iterrows()}
    for r in rows:
        meta = clean_by_url.get(r["url"], {})
        r["title"] = meta.get("title", "")
        r["media_name"] = meta.get("media_name", "")
        # Use title + first 400 words as the n-gram source, matching what we embedded.
        body_words = (meta.get("full_text") or "").split()
        r["text_sample"] = (meta.get("title", "") + " " + " ".join(body_words[:400])).strip()

    return vecs, rows


def restrict_to_canonical(vecs, rows):
    """Drop non-canonical dedupe members so syndicates don't dominate clusters."""
    if not os.path.exists(DEDUP_CSV):
        print(f"[warn] {DEDUP_CSV} missing; clustering all articles")
        return vecs, rows
    dedup = pd.read_csv(DEDUP_CSV)
    canonical_urls = set(dedup[dedup.is_canonical.astype(str).str.lower().isin(["true", "1"])].url)
    keep = [i for i, r in enumerate(rows) if r["url"] in canonical_urls]
    seen_urls = set()
    # Guard against the same canonical URL showing up twice in the embeddings manifest
    # (can happen if the scraper caught the URL under two different topic queries).
    unique_idxs = []
    for i in keep:
        if rows[i]["url"] in seen_urls:
            continue
        seen_urls.add(rows[i]["url"])
        unique_idxs.append(i)
    print(f"[dedup] kept {len(unique_idxs)} canonical articles "
          f"(dropped {len(rows) - len(unique_idxs)} non-canonical + URL duplicates)")
    return vecs[unique_idxs], [rows[i] for i in unique_idxs]


def normalize(vecs):
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def cluster(sims, threshold, n):
    uf = UnionFind(n)
    rows, cols = np.where(np.triu(sims >= threshold, k=1))
    for i, j in zip(rows, cols):
        uf.union(int(i), int(j))
    clusters = defaultdict(list)
    for idx in range(n):
        clusters[uf.find(idx)].append(idx)
    return list(clusters.values())


def cluster_centroid_idx(members, sims):
    """Return the local index of the most-central article — highest mean sim to others."""
    if len(members) == 1:
        return members[0]
    sub = sims[np.ix_(members, members)]
    np.fill_diagonal(sub, 0)
    mean_sim = sub.mean(axis=1)
    return members[int(np.argmax(mean_sim))]


def extract_ngrams_for_rows(rows, indices):
    counter = Counter()
    for idx in indices:
        counter.update(ngrams(tokenize(rows[idx]["text_sample"]), *NGRAM_RANGE))
    return counter


def distinguishing_ngrams(cluster_counter, corpus_counter, top_k, min_corpus_freq):
    """Rank n-grams by cluster-freq / corpus-freq. Filter rare corpus items."""
    scored = []
    for term, cf in cluster_counter.items():
        if cf < 2:
            continue
        total = corpus_counter.get(term, 0)
        if total < min_corpus_freq:
            continue
        score = cf / total
        scored.append((term, cf, total, score))
    scored.sort(key=lambda x: (x[3], x[1]), reverse=True)
    return scored[:top_k]


def run():
    vecs_all, rows_all = load()
    print(f"[load] {len(rows_all)} article embeddings")
    vecs, rows = restrict_to_canonical(vecs_all, rows_all)

    normed = normalize(vecs.astype(np.float32))
    print("[sim] pairwise cosine matrix...")
    sims = normed @ normed.T
    np.fill_diagonal(sims, 0.0)

    clusters = cluster(sims, SIM_THRESHOLD, len(rows))
    print(f"[cluster] at sim>={SIM_THRESHOLD}: {len(clusters)} clusters total, "
          f"{sum(1 for c in clusters if len(c) >= MIN_CLUSTER_SIZE)} with size >= {MIN_CLUSTER_SIZE}")

    big = [c for c in clusters if len(c) >= MIN_CLUSTER_SIZE]
    big.sort(key=len, reverse=True)
    noise_count = sum(len(c) for c in clusters if len(c) < MIN_CLUSTER_SIZE)
    print(f"[cluster] {noise_count} articles fall into below-threshold singletons/pairs (treated as noise)")

    # Pre-compute corpus n-gram counter for TF-like scoring.
    print("[ngram] building corpus n-gram counts...")
    corpus_counter = Counter()
    for i in range(len(rows)):
        corpus_counter.update(ngrams(tokenize(rows[i]["text_sample"]), *NGRAM_RANGE))

    # Assign cluster ids — big clusters get 0..K; rest get -1 (noise)
    assignment = [-1] * len(rows)
    cluster_summaries = []
    for cid, members in enumerate(big):
        for idx in members:
            assignment[idx] = cid
        outlets = Counter(rows[idx]["media_name"] for idx in members)
        topics = Counter(rows[idx]["topic"] for idx in members)
        ngram_counter = extract_ngrams_for_rows(rows, members)
        central_local = cluster_centroid_idx(members, sims)
        # Articles sorted by sim to the central one (descending)
        central_row_sims = sims[central_local, members]
        order = np.argsort(-central_row_sims)
        representatives = [members[int(o)] for o in order[:TOP_ARTICLES_PER_CLUSTER]]
        cluster_summaries.append({
            "cluster_id": cid,
            "size": len(members),
            "central_idx": central_local,
            "representatives": representatives,
            "outlets": outlets,
            "topics": topics,
            "distinguishing_ngrams": distinguishing_ngrams(
                ngram_counter, corpus_counter, TOP_NGRAMS_PER_CLUSTER, MIN_CORPUS_FREQ
            ),
            "members": members,
        })

    # Write per-article CSV assignment
    out_rows = []
    for i, r in enumerate(rows):
        out_rows.append({
            "url": r["url"],
            "cluster_id": assignment[i] if assignment[i] >= 0 else "",
            "article_topic": r["topic"],
            "media_name": r["media_name"],
            "title": r["title"],
        })
    pd.DataFrame(out_rows).to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"[write] {OUT_CSV}: {len(out_rows)} rows")

    # Write markdown report
    write_report(cluster_summaries, rows, noise_count, len(rows))
    print(f"[write] {OUT_MD}")


def write_report(summaries, rows, noise_count, total):
    lines = []
    lines.append("# Emergent Narrative Clusters\n")
    lines.append(
        f"Agglomerative clustering (union-find, cosine ≥ {SIM_THRESHOLD}) over "
        f"{total} dedupe-canonical article embeddings. "
        f"{len(summaries)} clusters of size ≥ {MIN_CLUSTER_SIZE}; "
        f"{noise_count} articles in smaller groups (noise).\n"
    )
    lines.append(
        f"Each cluster lists its most-central article, dominant outlets, the "
        f"MediaCloud topic labels its members were pulled under (cross-topic bleed), "
        f"distinguishing n-grams vs the rest of the corpus, and the top "
        f"{TOP_ARTICLES_PER_CLUSTER} representative articles by closeness to the cluster center.\n"
    )

    for s in summaries:
        central = rows[s["central_idx"]]
        lines.append(f"## Cluster {s['cluster_id']} — {s['size']} articles\n")
        lines.append(f"**Central article**: [{central['media_name']}] {central['title']}")
        lines.append(f"  {central['url']}")
        outlets = ", ".join(f"{o} ({n})" for o, n in s["outlets"].most_common(TOP_OUTLETS_PER_CLUSTER))
        if len(s["outlets"]) > TOP_OUTLETS_PER_CLUSTER:
            outlets += f", … (+{len(s['outlets']) - TOP_OUTLETS_PER_CLUSTER} more)"
        lines.append(f"\n**Outlets**: {outlets}")
        topics = ", ".join(f"{t} ({n})" for t, n in s["topics"].most_common())
        lines.append(f"**MediaCloud topics**: {topics}")
        ngram_line = ", ".join(
            f"'{term}' ({cf}/{total})"
            for term, cf, total, _ in s["distinguishing_ngrams"]
        )
        lines.append(f"**Distinguishing n-grams** (cluster-freq/corpus-freq): {ngram_line}")
        lines.append("\n**Representative articles**:")
        for rep_idx in s["representatives"]:
            r = rows[rep_idx]
            lines.append(f"- [{r['media_name']}] {r['title']}")
        lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    run()
