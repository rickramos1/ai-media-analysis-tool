"""Stage 4a of the cross-reference misinfo pipeline.

Embed each verified claim and each ORIGINAL article (chunked). Compute cosine
similarity per (article, claim) as the max similarity across that article's
chunks. Output ranked candidate matches — no LLM, no flagging. Stage 4b will
verify the top candidates with the LLM.
"""
import csv
import json
import os
import time
import urllib.request

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

csv.field_size_limit(2**30)

CLAIMS_JSON = "claims_verified.json"
FAMILIES_JSON = "claim_families_filtered.json"
ARTICLES_CSV = "articles_classified.csv"
OUTPUT_JSON = "stage4a_candidates.json"

CHUNK_WORDS = 1000  # words per article chunk
USE_FAMILIES = os.path.exists("claim_families_filtered.json")


def embed_batch(texts, batch_size=16):
    """Embed a list of strings. Returns np.array of shape (N, dim)."""
    vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        payload = json.dumps({"model": EMBED_MODEL, "input": batch}).encode("utf-8")
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        vectors.extend(data["embeddings"])
        if (i // batch_size) % 5 == 0:
            print(f"    embedded {min(i + batch_size, len(texts))}/{len(texts)}")
    arr = np.array(vectors, dtype=np.float32)
    # L2-normalize so dot product == cosine
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr = arr / np.clip(norms, 1e-10, None)
    return arr


def chunk_article(text, chunk_words=CHUNK_WORDS):
    words = text.split()
    if not words:
        return []
    return [" ".join(words[i:i + chunk_words]) for i in range(0, len(words), chunk_words)]


def run():
    claims = []
    if USE_FAMILIES:
        # Use canonical family claims instead of raw per-refutation texts.
        # Each family's `canonical_claim` is what we embed and match against;
        # its members carry the provenance (original fact-checks) for Stage 4b.
        with open(FAMILIES_JSON) as f:
            fams = json.load(f)["families"]
        for fam in fams:
            # Aggregate provenance from all members
            outlets = sorted({m.get("fact_check_outlet") for m in fam.get("members", []) if m.get("fact_check_outlet")})
            urls = sorted({m.get("fact_check_url") for m in fam.get("members", []) if m.get("fact_check_url")})
            sources = sorted({m.get("claim_source") for m in fam.get("members", []) if m.get("claim_source")})
            topics = sorted({m.get("topic") for m in fam.get("members", []) if m.get("topic")})
            claims.append({
                "claim_id": fam["id"],
                "claim_text": fam["canonical_claim"],
                "claim_source": "; ".join(sources)[:200] or "(various)",
                "verification_basis": "family",
                "refutation": f"Debunked by: {', '.join(outlets)}",
                "fact_check_outlet": ", ".join(outlets),
                "fact_check_url": urls[0] if urls else None,
                "fact_check_urls_all": urls,
                "topic": ", ".join(topics),
                "member_claims": fam.get("members", []),
            })
        print(f"[claims] using claim FAMILIES mode — {len(claims)} canonical claims to embed")
    else:
        with open(CLAIMS_JSON) as f:
            verified = json.load(f)
        seen_texts = set()
        for v in verified:
            for r in v["refutations"]:
                ct = (r.get("claim_text") or "").strip()
                if not ct or ct in seen_texts:
                    continue
                seen_texts.add(ct)
                claims.append({
                    "claim_id": len(claims),
                    "claim_text": ct,
                    "claim_source": v["claim_source"],
                    "verification_basis": v["verification_basis"],
                    "refutation": r.get("refutation", ""),
                    "fact_check_outlet": r.get("fact_check_outlet") or r.get("outlet"),
                    "fact_check_url": r.get("fact_check_url"),
                    "topic": r.get("topic"),
                })
        print(f"[claims] {len(claims)} unique claim-texts to embed")

    # Load ORIGINAL articles
    df = pd.read_csv(ARTICLES_CSV, dtype=str, keep_default_na=False, encoding="utf-8")
    originals = df[df["article_type"] == "ORIGINAL"].reset_index(drop=True)
    print(f"[articles] {len(originals)} ORIGINAL articles to process")

    # Build chunks: flat list with article_idx annotation for fan-in later
    chunk_texts = []
    chunk_article_idx = []
    for art_idx, row in originals.iterrows():
        chunks = chunk_article(f"{row['title']}. {row['full_text']}")
        for ch in chunks:
            chunk_texts.append(ch)
            chunk_article_idx.append(art_idx)
    print(f"[chunks] {len(chunk_texts)} total chunks (avg {len(chunk_texts)/max(1,len(originals)):.1f} per article)")

    # Embed claims
    print("[embed] claims...")
    t0 = time.time()
    claim_vecs = embed_batch([c["claim_text"] for c in claims])
    print(f"[embed] claims done in {time.time()-t0:.1f}s, shape={claim_vecs.shape}")

    # Embed chunks
    print("[embed] article chunks...")
    t0 = time.time()
    chunk_vecs = embed_batch(chunk_texts)
    print(f"[embed] chunks done in {time.time()-t0:.1f}s, shape={chunk_vecs.shape}")

    # Persist embeddings for reuse (BACKLOG: topic clustering / dedup / semantic gate).
    # Saved as L2-normalized 768-dim vectors; cosine == dot product.
    np.save("embeddings_article_chunks.npy", chunk_vecs)
    np.save("embeddings_claims.npy", claim_vecs)
    chunk_manifest = [
        {
            "chunk_idx": i,
            "article_idx": int(chunk_article_idx[i]),
            "article_url": originals.at[int(chunk_article_idx[i]), "url"],
            "article_title": originals.at[int(chunk_article_idx[i]), "title"],
            "article_outlet": originals.at[int(chunk_article_idx[i]), "media_name"],
            "article_topic": originals.at[int(chunk_article_idx[i]), "topic"],
        }
        for i in range(len(chunk_texts))
    ]
    with open("embeddings_article_chunks_manifest.json", "w") as f:
        json.dump({"model": EMBED_MODEL, "dim": int(chunk_vecs.shape[1]), "chunks": chunk_manifest}, f)
    with open("embeddings_claims_manifest.json", "w") as f:
        json.dump({"model": EMBED_MODEL, "dim": int(claim_vecs.shape[1]),
                   "claims": [{"claim_id": c["claim_id"], "claim_text": c["claim_text"]} for c in claims]}, f)
    print(f"[persist] embeddings_article_chunks.npy ({chunk_vecs.nbytes/1e6:.1f} MB), embeddings_claims.npy, manifests written")

    # Similarity: sim[chunk, claim] = chunk_vecs @ claim_vecs.T
    sim_matrix = chunk_vecs @ claim_vecs.T  # (N_chunks, N_claims)

    # For each (article, claim), take the max across chunks of that article
    n_articles = len(originals)
    n_claims = len(claims)
    article_claim_sim = np.full((n_articles, n_claims), -1.0, dtype=np.float32)
    for ci, ai in enumerate(chunk_article_idx):
        row = sim_matrix[ci]
        article_claim_sim[ai] = np.maximum(article_claim_sim[ai], row)

    # Build output: for each article, its top-K claim matches
    top_k = 3
    results = []
    for art_idx, row in originals.iterrows():
        sims = article_claim_sim[art_idx]
        top = np.argsort(-sims)[:top_k]
        results.append({
            "article_url": row["url"],
            "article_title": row["title"],
            "article_outlet": row["media_name"],
            "article_topic": row["topic"],
            "top_matches": [
                {
                    "similarity": float(sims[i]),
                    "claim_id": claims[i]["claim_id"],
                    "claim_text": claims[i]["claim_text"],
                    "claim_source": claims[i]["claim_source"],
                    "fact_check_outlet": claims[i]["fact_check_outlet"],
                    "fact_check_url": claims[i]["fact_check_url"],
                }
                for i in top
            ],
        })

    # Also emit the full similarity summary: histogram + top-100 pairs across corpus
    flat_pairs = []
    for ai in range(n_articles):
        for ci in range(n_claims):
            flat_pairs.append((float(article_claim_sim[ai, ci]), ai, ci))
    flat_pairs.sort(reverse=True)

    output = {
        "claims": claims,
        "per_article": results,
        "top_pairs_global": [
            {
                "similarity": s,
                "article_url": originals.at[ai, "url"],
                "article_title": originals.at[ai, "title"],
                "article_outlet": originals.at[ai, "media_name"],
                "claim_text": claims[ci]["claim_text"],
                "claim_source": claims[ci]["claim_source"],
                "fact_check_outlet": claims[ci]["fact_check_outlet"],
            }
            for s, ai, ci in flat_pairs[:100]
        ],
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[write] {OUTPUT_JSON}")

    # Report similarity distribution
    sims_all = article_claim_sim.flatten()
    thresholds = [0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]
    print()
    print("Similarity distribution (article × claim pairs):")
    print(f"  total pairs: {len(sims_all)}")
    print(f"  mean: {sims_all.mean():.3f}, max: {sims_all.max():.3f}, p95: {np.percentile(sims_all, 95):.3f}, p99: {np.percentile(sims_all, 99):.3f}")
    print()
    print("Pairs above threshold (candidates for Stage 4b):")
    for t in thresholds:
        count = int((sims_all >= t).sum())
        print(f"  sim >= {t:.2f}:  {count:>5d} pairs  ({count / n_articles:.2f} per article)")


if __name__ == "__main__":
    run()
