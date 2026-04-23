# Backlog

Future work, not yet scoped or scheduled. For what's shipped, see `CLAUDE.md` (pipeline diagram) and `FINDINGS.md` (latest run output).

## Cross-reference misinfo detection — follow-ups

Stages 1–5 of the original cross-reference spec are shipped (`article_classifier.py`, `claim_extractor.py`, `stage3_filter.py`, `claim_normalizer.py`, `stage4a_retrieval.py`, `stage4b_verify.py`, `stage5_report.py`). `stage5_report.py` regenerates `misinfo_carriers_by_article.csv` + `FINDINGS.md` from the Stage 4b verdicts. What's still open:

- **Claim extraction test set.** The 6 original True-verdict articles were called out as a natural starter set for evaluating Stage 2 prompt quality; no test set / regression harness exists yet.
- **Stage 3.5 normalizer chunking.** `claim_normalizer.py` makes one big LLM call to cluster all claims. At ≥150 input claims with `num_ctx=8192`, qwen3 sometimes returns prose instead of JSON. Proper fix is batching ~40 claims per call and merging family clusters by fuzzy matching canonical claim texts. Stage 4a's fallback path masks the failure today.
- **Stage 4b UNKNOWN rate.** Currently ~20% UNKNOWN on first pass, recoverable by re-running with the same `num_predict=1500`. Worth investigating whether a tighter prompt or a different stop pattern gets UNKNOWN under 5% without the re-run.

## Scraper: Cloudflare-tier bypass

UA rotation + realistic headers clears static WAF heuristics. Cloudflare-tier blocks (Newsweek, Forbes, ABC News, parts of WaPo) still 403. Next tier is `curl_cffi` (TLS fingerprint matching) or `playwright` (real browser). Measure what fraction of the corpus we're losing before committing — playwright adds real operational weight.

## Article vectorization & topic clustering

Embed each article (`nomic-embed-text` is already on bigdoggie) and cluster to surface topic groupings beyond the MediaCloud query labels. Useful for:

- Replacing the keyword-based topic relevance gate (`misinfo_detector.TOPIC_TERMS`) with semantic relevance — drop off-topic articles by cosine similarity to a topic centroid instead of keyword presence. Would also fix the silent-filter failure mode when query labels drift out of sync with `TOPIC_TERMS`.
- Discovering emergent narratives across outlets that don't match a predefined query.
- Deduplicating near-identical syndicated coverage before sending to the LLM.

## N-gram analysis of article topics

Run n-gram (bi/trigram) extraction across article bodies grouped by topic, ideology tag, or cluster. Surfaces recurring framings and rhetorical patterns ("trad wife", "post-abortion regret", etc.) that single-keyword analysis misses. Complements `keyword_analysis.py`.

## Storage layer: DuckDB + GCP scalability

Move canonical storage off CSVs onto DuckDB (single-file, columnar, SQL — drop-in for the local pipeline). The claims + families + verdicts + articles graph is relational and doesn't fit CSVs well; today we round-trip through JSON and re-key on every stage. Plan migration path to GCP (GCS-backed Parquet, BigQuery, or DuckDB-over-GCS) for scale. Keep CSV export as a downstream artifact for compatibility.
