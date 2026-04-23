# Backlog

Future work, not yet scoped or scheduled. For what's shipped, see `CLAUDE.md` (pipeline diagram) and `FINDINGS.md` (latest run output).

## Cross-reference misinfo detection — follow-ups

Stages 1–5 of the original cross-reference spec are shipped (`article_classifier.py`, `claim_extractor.py`, `stage3_filter.py`, `claim_normalizer.py`, `stage4a_retrieval.py`, `stage4b_verify.py`, `stage5_report.py`). `stage5_report.py` regenerates `misinfo_carriers_by_article.csv` + `FINDINGS.md` from the Stage 4b verdicts. What's still open:

- **Claim extraction test set.** The 6 original True-verdict articles were called out as a natural starter set for evaluating Stage 2 prompt quality; no test set / regression harness exists yet.
- **Stage 3.5 normalizer chunking.** `claim_normalizer.py` makes one big LLM call to cluster all claims. At ≥150 input claims with `num_ctx=8192`, qwen3 sometimes returns prose instead of JSON. Proper fix is batching ~40 claims per call and merging family clusters by fuzzy matching canonical claim texts. Stage 4a's fallback path masks the failure today.
- **Stage 4b UNKNOWN rate (lower priority).** Post-recovery rate is 0.4% (9/2,147) on the current corpus — already well under the original 5% target. The open work is only about eliminating the manual re-run step; carrier yield is not being hurt.

## Scraper: Cloudflare-tier bypass

UA rotation + realistic headers clears static WAF heuristics. Cloudflare-tier blocks (Newsweek, Forbes, ABC News, parts of WaPo) still 403. Next tier is `curl_cffi` (TLS fingerprint matching) or `playwright` (real browser). Measure what fraction of the corpus we're losing before committing — playwright adds real operational weight.

## Article vectorization — wire up the shadow components

Two shadow-mode artifacts are shipped; both persist `nomic-embed-text` embeddings of every scraped article (title + first 400 words) and reuse the same `.npy`:

- **Semantic topic gate** (`semantic_topic_gate.py`): scores each article against a per-topic centroid built from the MediaCloud query text plus seed articles. Current regex gate (`TOPIC_TERMS`) silently drops 200+ on-topic articles at every threshold probed; the overlap between ORIGINAL (p10 ≈ 0.71) and OTHER (p90 ≈ 0.77) score distributions means no clean flat cut.
- **Syndicated-coverage dedupe** (`dedupe_articles.py`): clusters near-duplicate articles (cosine ≥ 0.95) via union-find. On the current corpus 19.2% of articles (286/1,486) are in multi-article clusters — a mix of scraping duplicates and cross-outlet syndicates. 28/65 flagged carriers in the last run are in such clusters.

Open follow-ups:

- **Hybrid gate wire-up.** Change `filter_eligible` to admit `regex_pass OR semantic_score ≥ 0.70` — strictly additive, Stage 1 handles residual false positives. Ship alongside dedupe so one end-to-end re-run validates both.
- **Dedupe wire-up.** Filter non-canonical cluster members before Stage 1. ~19% fewer LLM cycles across Stages 1/2/4b; cleaner syndication rollups in reviewer outputs.
- **Per-topic thresholds or seed-set curation.** If the hybrid gate's recall/precision isn't enough, the cleanest next lever is per-topic calibration or hand-curated seed articles per topic (semantic gate already supports seed mixing in the centroid).
- **Topic clustering for emergent narratives.** The embedding infra is in place; no script yet that clusters articles independent of the MediaCloud query labels to surface narratives that don't match a predefined topic.

## N-gram analysis of article topics

Run n-gram (bi/trigram) extraction across article bodies grouped by topic, ideology tag, or cluster. Surfaces recurring framings and rhetorical patterns ("trad wife", "post-abortion regret", etc.) that single-keyword analysis misses. Complements `keyword_analysis.py`.

## Storage layer: DuckDB + GCP scalability

Move canonical storage off CSVs onto DuckDB (single-file, columnar, SQL — drop-in for the local pipeline). The claims + families + verdicts + articles graph is relational and doesn't fit CSVs well; today we round-trip through JSON and re-key on every stage. Plan migration path to GCP (GCS-backed Parquet, BigQuery, or DuckDB-over-GCS) for scale. Keep CSV export as a downstream artifact for compatibility.
