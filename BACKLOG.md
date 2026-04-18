# Backlog

Future work, not yet scoped or scheduled.

## Cross-reference misinfo detection (next major iteration)

The initial `misinfo_detector.py` asked the LLM a bad question ("is this article misleading?") and in a 545-article run produced 377 Unknown (76%) and 6 False-positive True verdicts — all 6 were fact-check journalism *reporting on* misinformation, not carrying it. That failure mode points to a better architecture: treat fact-check articles as a signal source, not noise.

### Architecture

```
Stage 1 — classify each article
  {FACT_CHECK, ORIGINAL, OTHER}
  (LLM call, small prompt, cheap)

Stage 2 — for FACT_CHECK articles, extract structured claims
  For each debunked claim, emit:
    - claim_text            (the specific statement being refuted)
    - claim_source          (outlet/person that made the claim, if named)
    - refutation            (what evidence the fact-check cites)
    - evidence_sources      (cited studies, experts, regulators)
    - fact_check_outlet     (the article we extracted this from)
    - ideology_tag          (of the fact-check outlet)
  → "debunked claims database"

Stage 3 — require multiple independent debunks
  Admit a claim to the canonical database only if ≥2 fact-check outlets
  with different ideology tags refute it. Avoids one-outlet editorial
  assertions becoming "ground truth".

Stage 4 — for ORIGINAL articles, search for claim-carriers
  (a) Embedding-based retrieval: embed each debunked claim and each
      ORIGINAL article; return top-K candidate matches by cosine.
  (b) LLM verification: "Article X says: [quote]. Debunked claim Y:
      [claim]. Does X present Y as true?" — binary yes/no/uncertain.
  Flag article iff verification is "yes".

Stage 5 — audit trail
  Every flagged article carries the claim IDs, the fact-check sources
  that refuted them, and the specific passage in the article that
  matches. Human reviewer can inspect before publication.
```

### Honest limits

- Fact-checkers are not absolute ground truth. Require multi-outlet, multi-ideology debunks (Stage 3) and keep a human reviewer in the loop.
- Embedding retrieval (Stage 4a) depends on claim-text being a good query — short or vague claims will retrieve noise. Stage 4b's LLM verification is the real gate.
- Claim extraction (Stage 2) is the hardest prompt. Needs careful few-shot examples and a test set. The 6 current True-verdict articles are a natural starter set.

### Dependencies

- Stage 4a benefits from the existing "Article vectorization & topic clustering" item above — shared embedding infrastructure.
- Stage 3 relies on `source_ideology_tagger.py` coverage. Verify all fact-check outlets in our corpus are tagged before running Stage 3.
- Storage: claims database should be a DuckDB table (not CSV) from day one — see "Storage layer" item below. Relational joins (claims × articles × outlets × ideology) don't fit CSVs well.

### Bootstrap path

1. Run claim extraction (Stage 2) on the 6 existing True-verdict articles as a proof of concept. Evaluate claim quality manually.
2. Add a Stage 1 classifier to the existing pipeline, re-run at small scale to quantify FACT_CHECK vs ORIGINAL proportions.
3. If Stage 2 claims look usable, build the claim database table.
4. Then tackle Stage 4 retrieval + verification.

## Article vectorization & topic clustering

Embed each article (e.g. `nomic-embed-text` already on bigdoggie, or sentence-transformers locally) and cluster to surface topic groupings beyond the MediaCloud query labels. Useful for:
- Replacing the keyword-based topic relevance gate with semantic relevance (drop off-topic articles by cosine similarity to topic centroid instead of keyword presence).
- Discovering emergent narratives across outlets that don't match a predefined query.
- Deduplicating near-identical syndicated coverage before sending to the LLM.

## N-gram analysis of article topics

Run n-gram (bi/trigram) extraction across article bodies grouped by topic, ideology tag, or cluster. Surfaces recurring framings and rhetorical patterns ("trad wife", "post-abortion regret", etc.) that single-keyword analysis misses. Complements `keyword_analysis.py`.

## Storage layer: DuckDB + GCP scalability

Move canonical storage off CSVs onto DuckDB (single-file, columnar, SQL — drop-in for the local pipeline). Plan migration path to Google Cloud (GCS-backed Parquet, BigQuery, or DuckDB-over-GCS) for scale. Keep CSV export as a downstream artifact for compatibility.
