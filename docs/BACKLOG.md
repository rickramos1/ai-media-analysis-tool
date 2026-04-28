# Backlog

Future work, not yet scoped or scheduled. For what's shipped, see `CLAUDE.md` (pipeline diagram) and `FINDINGS.md` (latest run output).

## Cross-reference misinfo detection — follow-ups

Stages 1–5 of the original cross-reference spec are shipped (`article_classifier.py`, `claim_extractor.py`, `stage3_filter.py`, `claim_normalizer.py`, `stage4a_retrieval.py`, `stage4b_verify.py`, `stage5_report.py`). `stage5_report.py` regenerates `misinfo_carriers_by_article.csv` + `FINDINGS.md` from the Stage 4b verdicts. What's still open:

- **Claim extraction test set (Stage 2).** The 6 original True-verdict articles were called out as a natural starter set; no Stage 2 test set / regression harness exists yet. Stage 4b now has one (see "Stage 4b precision harness" below) — Stage 2 still doesn't.
- ~~**Stage 3.5 normalizer chunking.**~~ Shipped. `claim_normalizer.py` now chunks the input into batches of `--chunk-size` (default 40), uses Ollama's `"think": false` toggle (qwen3 silently ignores the `/no_think` prompt directive), and merges families across batches by fuzzy-matching `canonical_claim` text. Per-batch parse failures degrade to singleton families. On a 198-claim run: 4 of 5 batches parse cleanly, ~143 global families. Stage 4a's fallback path is preserved as a safety net.
- ~~**Apply `"think": false` to the other LLM stages.**~~ Shipped across all five LLM-using scripts (`article_classifier.py`, `claim_extractor.py`, `claim_normalizer.py`, `stage4b_verify.py`, `misinfo_detector.py`). Smoke test on Stage 1 showed ~0.7s/call vs the previous ~9s baseline (10×). Open: re-measure full-pipeline throughput after the next run, then drop `num_predict` from 1500 → ~400 on Stage 2/4b since the bumps are no longer load-bearing.
- **Per-batch retry on parse failure.** Batch 1 of the 198-claim test failed to parse (24.9s vs 17-21s for the others — likely budget exhaustion). A single retry with `num_predict=2500` would catch most of these without changing the default. Currently the singleton-fallback masks it acceptably.
- **Stage 4b UNKNOWN rate (lower priority).** Post-recovery rate is 0.4% (9/2,147) on the current corpus — already well under the original 5% target. The open work is only about eliminating the manual re-run step; carrier yield is not being hurt.

### External fact-check seed (recall lever) — **VALIDATED**

`pipeline/external_factchecks.py` pulls debunked-claim records from the Google Fact Check Tools API (which aggregates ClaimReview-marked content from publishers worldwide), filters to women's-health and to "false/misleading"-style verdicts, dedupes against in-corpus URLs, and emits a `claims.json`-shaped file. Stage 3 accepts `--extra-input <path>` to union it in.

**Validated end-to-end.** Default-query run pulled 211 raw API records → 54 women's-health-relevant after filtering and de-duplication. Outlet contributions: politifact (14), factcheck.afp.com (9), usatoday (8), snopes (5), apnews (5), factcheck.org (4) — exactly the fact-checkers MediaCloud doesn't surface. Stage 3 promoted 17 → 36 canonical sources after the initial merge; subsequent audit removed 11 false-positives (election politicians, symmetric pro-choice claims, ProPublica-as-attacked-target) → 25 final canonical sources. End-to-end downstream impact: previous run had 117 carrying verdicts / 65 articles; new run has 315 carrying verdicts / 136 articles after audit. Open follow-ups:

- **Refutation body is shallow.** ClaimReview gives a textual rating ("False") but no refutation prose; the adapter writes `f"ClaimReview rating: {rating}"` as a placeholder. Stage 4b doesn't currently read the refutation, so this is fine for now — but if downstream features start using it, scrape the linked fact-check URL for the body.
- **Topic-relevance filter is regex-only.** Reuses `WOMENS_HEALTH_RX` from `claim_normalizer.py`. Same caveats — false negatives if vocabulary lags. Could swap to semantic gate against the topic centroids.

### Stage 4b precision harness (accuracy lever) — **VALIDATED**

`pipeline/gold_set_build.py` + `pipeline/gold_set_eval.py` give a stratified labeling workflow against `stage4b_verdicts.json`. Build samples N pairs per verdict class (default 25, total 100); reviewer or cloud-LLM judge fills the verdict column; eval prints confusion matrix + per-class precision/recall/F1 + carrier FP/FN listings. `gold_set_eval.py` auto-detects `human_verdict` or `cloud_llm_verdict` column and supports `--judge-col` / `--llm-col` overrides. `pipeline/gold_set_reverify.py` provides a targeted reverification loop for testing prompt/model changes against the same labels.

**100-row gold set labeled by Claude Opus 4.7 acting as judge.** Measured against qwen3:14b at temperature=0:
- Overall accuracy: 90.0%
- Carrier precision: **0.84** (4 false-positives in 25 stratified)
- Carrier recall: **1.00** (no real carriers missed)
- Per-class F1: carrying 0.913, debunking 0.962, neutral_reporting 0.844, irrelevant 0.877
- 3 of 4 carrier FPs share the **quote-then-refute** pattern (article quotes the claim, refutes elsewhere; qwen3 misses the refutation)

Open follow-ups:

- **Re-label after material pipeline changes** (new claim families, new model) so precision can be tracked over time.
- **Expand to ~400 rows** before benchmarking candidate replacement models. 25 carrying samples gives ±15% CI on precision — too wide to confidently distinguish 0.84 from 0.92 across model candidates.
- **Build the same harness for Stage 2** (claim extraction quality). Same bones, different inputs (`claims.json` rows × per-claim `correct/wrong/missing` labels).
- **Spot-check carrier flags from center/left outlets** (cbsnews 3, usatoday 1, nytimes 1, vox 1) — likely additional quote-then-refute false positives.

### Stage 4b carrier-precision improvement attempts — both failed, see research doc

Two prompt-engineering attempts to push the 0.84 carrier-precision ceiling **both regressed**:
1. Stage 4b prompt rewrite ("scan whole article for refutation before classifying"): precision 0.84 → 0.50, recall 1.00 → 0.36. Reverted.
2. Post-processing refutation-detection second pass (`pipeline/stage4b_refute_check.py`): hand-audit of 27 demotions found ~57% wrong (qwen3 routinely treated supportive citations as refutations). Reverted.

Diagnosis: qwen3:14b cannot reliably distinguish "this paragraph supports the claim" vs "this paragraph refutes the claim" when both appear in the same article body. **The fix has to be a better model, not a better prompt.** Full analysis: `docs/local_llm_accuracy_research.md`. The research project will benchmark candidate replacement models (Phi-4-reasoning, gpt-oss-safeguard-20b, Gemma 3 12B, etc.) against the existing gold set.

### Stage 4b structural-output enforcement — **SHIPPED**

Both `pipeline/claim_normalizer.py` (Stage 3.5) and `pipeline/stage4b_verify.py` (Stage 4b) now pass an Ollama JSON Schema as the `format` parameter. Token-level grammar-constrained generation guarantees the response parses as valid JSON matching the schema; Stage 4b's `verdict` field is constrained to the four-value `enum`. Eliminates the prose-summary regression mode (Stage 3.5) and structurally impossible to return invalid verdict strings (Stage 4b).

### Stage 4b evidence_quote hallucination — **SHIPPED + retroactively cleaned**

Audit on the 315 carrying verdicts found 91 (29%) had `evidence_quote` values that were not literal substrings of the article body — 66 pure paraphrases, 25 stitched abridgments. `quote_in_article()` validator added to `pipeline/stage4b_verify.py` auto-nulls hallucinations on future runs. `pipeline/stage4b_quote_reextract.py` ran a one-shot retroactive cleanup with a strict-literal prompt + the validator + 1 retry: 79/91 (87%) recovered as verifiable literal quotes, 12/91 (13%) honestly nulled. Post-cleanup hallucination rate: 0%.

Open follow-up: bake the strict-literal prompt into the main `verify()` so quotes are correct at generation time instead of post-hoc validated. Smoke test (5/5 clean on first attempt) suggests this would work without regression risk.

## Scraper: Cloudflare-tier bypass

UA rotation + realistic headers clears static WAF heuristics. Cloudflare-tier blocks (Newsweek, Forbes, ABC News, parts of WaPo) still 403. Next tier is `curl_cffi` (TLS fingerprint matching) or `playwright` (real browser). Measure what fraction of the corpus we're losing before committing — playwright adds real operational weight.

## Article vectorization — shadow components wired in

Two shadow-mode artifacts are shipped; both persist `nomic-embed-text` embeddings of every scraped article (title + first 400 words) and reuse the same `.npy`:

- **Semantic topic gate** (`pipeline/semantic_topic_gate.py`): scores each article against a per-topic centroid built from the MediaCloud query text plus seed articles. The original regex gate (`TOPIC_TERMS`) silently dropped 200+ on-topic articles; the overlap between ORIGINAL (p10 ≈ 0.71) and OTHER (p90 ≈ 0.77) score distributions means no clean flat cut, so the wire-up is *additive* — semantic admits supplement regex rather than replacing it.
- **Syndicated-coverage dedupe** (`pipeline/dedupe_articles.py`): clusters near-duplicate articles (cosine ≥ 0.95) via union-find. On the current corpus 19.2% of articles (286/1,486) are in multi-article clusters — a mix of scraping duplicates and cross-outlet syndicates.

**Shipped.** `filter_eligible` in `misinfo_detector.py` now admits `passes_wc AND (regex_pass OR semantic_score ≥ SEMANTIC_GATE_THRESHOLD) AND is_canonical`. Threshold defaults to 0.70 (override via env `SEMANTIC_GATE_THRESHOLD`). The dedupe map is joined on `(url, topic)` so URL-collision canonicals aren't double-dropped. `filter_eligible` accepts `hybrid=False` for shadow comparisons; `semantic_topic_gate.py`'s calibration report passes that to keep the regex baseline clean. Smoke counts on the current corpus: 1,159 → 988 eligible (-171 net = +63 semantic-only admits, -234 dedupe drops that legacy would have routed to Stage 1).

Open follow-ups:

- **Validation rerun.** No end-to-end rerun yet — Stage 1+2+4b are the slow ones. Compare carrier yield/precision against the last shipped run before declaring this wired-up officially "good."
- **Per-topic thresholds or seed-set curation.** If hybrid gate recall/precision isn't enough after the validation rerun, the cleanest next lever is per-topic calibration or hand-curated seed articles per topic (semantic gate already supports seed mixing in the centroid).
- **Topic clustering for emergent narratives.** Shipped (`pipeline/cluster_articles.py` → `docs/narrative_clusters.md`).

## N-gram analysis of article topics

Run n-gram (bi/trigram) extraction across article bodies grouped by topic, ideology tag, or cluster. Surfaces recurring framings and rhetorical patterns ("trad wife", "post-abortion regret", etc.) that single-keyword analysis misses. Complements `keyword_analysis.py`.

## Storage layer: DuckDB + GCP scalability

Move canonical storage off CSVs onto DuckDB (single-file, columnar, SQL — drop-in for the local pipeline). The claims + families + verdicts + articles graph is relational and doesn't fit CSVs well; today we round-trip through JSON and re-key on every stage. Plan migration path to GCP (GCS-backed Parquet, BigQuery, or DuckDB-over-GCS) for scale. Keep CSV export as a downstream artifact for compatibility.
