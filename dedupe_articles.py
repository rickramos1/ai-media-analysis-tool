"""Syndicated-coverage dedupe (shadow mode).

Finds near-duplicate articles using the embeddings persisted by
`semantic_topic_gate.py` (`article_topic_embeddings.npy`) and emits
a dedup map that downstream stages can use to skip syndicated copies.

Two passes:
1. URL dedupe — same url showing up twice (e.g. caught by two topic queries).
2. Semantic dedupe — cosine ≥ threshold on title+lead embeddings, clustered
   with union-find. Canonical = highest word count within the cluster.

Outputs:
- `article_dedup_map.csv`: url, cluster_id, cluster_size, is_canonical,
  canonical_url, max_sim_to_canonical, article_topic, media_name, title, wc
- Stdout: distribution of cluster sizes at candidate thresholds + pick of default
"""
import json
import os

import numpy as np
import pandas as pd

EMB_NPY = "article_topic_embeddings.npy"
EMB_MANIFEST = "article_topic_embeddings_manifest.json"
CLEAN_CSV = "womens_health_articles_text_clean.csv"
OUT_CSV = "article_dedup_map.csv"

CANDIDATE_THRESHOLDS = [0.90, 0.92, 0.95, 0.97]
DEFAULT_THRESHOLD = 0.95


def load():
    vecs = np.load(EMB_NPY)
    with open(EMB_MANIFEST) as f:
        manifest = json.load(f)
    urls = [a["url"] for a in manifest["articles"]]
    topics = [a["topic"] for a in manifest["articles"]]
    wcs = [a.get("wc") or 0 for a in manifest["articles"]]

    clean = pd.read_csv(CLEAN_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    meta_by_url = {r["url"]: r for _, r in clean.iterrows()}
    return vecs, urls, topics, wcs, meta_by_url


def normalize(vecs):
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


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


def cluster_at(sims, threshold, n):
    """Build clusters from upper-triangle of cosine sim matrix at threshold."""
    uf = UnionFind(n)
    # sims is NxN; only use upper triangle
    rows, cols = np.where(np.triu(sims >= threshold, k=1))
    for i, j in zip(rows, cols):
        uf.union(int(i), int(j))
    clusters = {}
    for idx in range(n):
        clusters.setdefault(uf.find(idx), []).append(idx)
    return clusters


def summarize_clusters(clusters):
    sizes = [len(members) for members in clusters.values()]
    total = sum(sizes)
    singletons = sum(1 for s in sizes if s == 1)
    multi = sum(1 for s in sizes if s > 1)
    redundant = sum(s - 1 for s in sizes if s > 1)
    biggest = max(sizes) if sizes else 0
    return {
        "total_articles": total,
        "total_clusters": len(clusters),
        "singletons": singletons,
        "multi_article_clusters": multi,
        "redundant_articles": redundant,
        "biggest_cluster": biggest,
    }


def run():
    vecs, urls, topics, wcs, meta_by_url = load()
    n = len(urls)
    print(f"[load] {n} article embeddings, dim={vecs.shape[1]}")

    # URL dedupe pass — collapse exact URL collisions first.
    url_to_idxs = {}
    for i, url in enumerate(urls):
        url_to_idxs.setdefault(url, []).append(i)
    url_collisions = {u: idxs for u, idxs in url_to_idxs.items() if len(idxs) > 1}
    print(f"[url-dedupe] {len(url_collisions)} URLs appear more than once "
          f"({sum(len(v) - 1 for v in url_collisions.values())} redundant rows)")

    normed = normalize(vecs.astype(np.float32))
    print("[sim] computing pairwise cosine matrix...")
    sims = normed @ normed.T
    # Zero diagonal so self-pairs don't count
    np.fill_diagonal(sims, 0.0)

    print("\nCandidate thresholds — cluster size distribution:")
    print(f"  {'thr':>5s} {'clusters':>9s} {'singletons':>11s} {'multi':>6s} {'redundant':>10s} {'biggest':>8s}")
    for thr in CANDIDATE_THRESHOLDS:
        clusters = cluster_at(sims, thr, n)
        s = summarize_clusters(clusters)
        print(f"  {thr:>5.2f} {s['total_clusters']:>9d} {s['singletons']:>11d} "
              f"{s['multi_article_clusters']:>6d} {s['redundant_articles']:>10d} "
              f"{s['biggest_cluster']:>8d}")

    print(f"\nEmitting dedup map at threshold {DEFAULT_THRESHOLD}")
    clusters = cluster_at(sims, DEFAULT_THRESHOLD, n)

    # Within each cluster, pick canonical = highest wc.
    rows = []
    for cluster_id, (_, members) in enumerate(clusters.items()):
        if len(members) == 1:
            idx = members[0]
            meta = meta_by_url.get(urls[idx], {})
            rows.append({
                "url": urls[idx],
                "cluster_id": cluster_id,
                "cluster_size": 1,
                "is_canonical": True,
                "canonical_url": urls[idx],
                "max_sim_to_canonical": 1.0,
                "article_topic": topics[idx],
                "media_name": meta.get("media_name", ""),
                "title": meta.get("title", ""),
                "wc": wcs[idx],
            })
            continue
        # Pick the member with the largest wc as canonical
        canonical_idx = max(members, key=lambda i: (wcs[i] or 0, -i))
        canonical_url = urls[canonical_idx]
        for idx in members:
            meta = meta_by_url.get(urls[idx], {})
            sim_to_canon = float(sims[idx, canonical_idx]) if idx != canonical_idx else 1.0
            rows.append({
                "url": urls[idx],
                "cluster_id": cluster_id,
                "cluster_size": len(members),
                "is_canonical": idx == canonical_idx,
                "canonical_url": canonical_url,
                "max_sim_to_canonical": round(sim_to_canon, 4),
                "article_topic": topics[idx],
                "media_name": meta.get("media_name", ""),
                "title": meta.get("title", ""),
                "wc": wcs[idx],
            })

    df = pd.DataFrame(rows).sort_values(["cluster_size", "cluster_id"], ascending=[False, True])
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"[write] {OUT_CSV}: {len(df)} rows")

    # Show biggest clusters for eyeball inspection
    big = df[df.cluster_size > 1].sort_values(["cluster_size", "cluster_id"], ascending=[False, True])
    shown = 0
    print(f"\nBiggest multi-article clusters at sim >= {DEFAULT_THRESHOLD}:")
    for cid, sub in big.groupby("cluster_id", sort=False):
        if shown >= 8:
            break
        print(f"\n  Cluster {cid} — size {len(sub)}:")
        for _, r in sub.iterrows():
            tag = "★" if r.is_canonical else " "
            print(f"    {tag} [{r.media_name:<22s}] wc={r.wc:>5d} sim={r.max_sim_to_canonical:.3f}  "
                  f"{r.title[:70]}")
        shown += 1

    # Stats at chosen threshold
    s = summarize_clusters(clusters)
    print(f"\n[summary at {DEFAULT_THRESHOLD}] {s['total_clusters']} clusters "
          f"({s['multi_article_clusters']} multi-article), "
          f"{s['redundant_articles']} redundant articles "
          f"({100 * s['redundant_articles'] / s['total_articles']:.1f}% of corpus)")


if __name__ == "__main__":
    run()
