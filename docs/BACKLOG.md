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

### Stage 4b precision harness (accuracy lever) — **VALIDATED + DROVE MODEL SWAP**

`pipeline/gold_set_build.py` + `pipeline/gold_set_eval.py` give a stratified labeling workflow against `stage4b_verdicts.json`. Build samples N pairs per verdict class (default 25, total 100); reviewer or cloud-LLM judge fills the verdict column; eval prints confusion matrix + per-class precision/recall/F1 + carrier FP/FN listings. `pipeline/gold_set_cloud_label.py` automates the cloud-judge step via the Anthropic API (defaults to `claude-opus-4-7`, 12-way parallel, ~35s for 100 rows, ~$2-3 cost). `pipeline/gold_set_bakeoff.py` runs N candidate models against the gold set in turn and prints a comparison table — used for the 2026-05-01 model swap. `pipeline/gold_set_reverify.py` provides a targeted reverification loop for testing prompt changes on a single model.

**Current state — `data/gold_set_labeled_v2.csv`** (rebuilt 2026-05-01, judged by claude-opus-4-7). The harness drove the swap from qwen3:14b to gpt-oss-safeguard:latest. Per-model numbers in the "Stage 4b carrier-precision improvement attempts" section above. Production pipeline (gpt-oss-safeguard) measured at **0.83 accuracy, 1.00 carrier precision, 0.54 carrier recall** on the gold set.

**Historical baseline** (`data/gold_set_labeled.csv`, 2026-04-28, no longer reproducible) reported 90.0% / 0.84 / 1.00 with qwen3:14b + format=schema. Same model file + code today produces ~50-56% agreement with the recorded verdicts; most plausible cause is an Ollama internal change between then and now.

Open follow-ups:

- **Re-label after material pipeline changes** (new claim families, new model) so precision can be tracked over time.
- **Expand to ~400 rows** before benchmarking candidate replacement models. 25 carrying samples gives ±15% CI on precision — too wide to confidently distinguish 0.84 from 0.92 across model candidates.
- **Build the same harness for Stage 2** (claim extraction quality). Same bones, different inputs (`claims.json` rows × per-claim `correct/wrong/missing` labels).
- **Spot-check carrier flags from center/left outlets** (cbsnews 3, usatoday 1, nytimes 1, vox 1) — likely additional quote-then-refute false positives.

### Stage 4b carrier-precision improvement attempts — resolved by model swap

Three prompt-engineering attempts on qwen3:14b all regressed:
1. Stage 4b prompt rewrite ("scan whole article for refutation before classifying"): precision 0.84 → 0.50, recall 1.00 → 0.36. Reverted.
2. Post-processing refutation-detection second pass (`pipeline/stage4b_refute_check.py`): hand-audit of 27 demotions found ~57% wrong. Reverted.
3. Bake strict-literal evidence_quote prompt into main `verify()`: most of measured regression turned out to be drift, not prompt — but added ~5pp regression on top. Reverted.

Conclusion was right — **the fix has to be a better model, not a better prompt** — and the 2026-05-01 model bake-off found the right replacement. `pipeline/gold_set_bakeoff.py` ran 5 candidates against the rebuilt 100-row gold set:

| Model | Accuracy | Carrier P | Carrier R | Carrier F1 |
|---|---|---|---|---|
| **gpt-oss-safeguard:latest** | **0.83** | **1.00** | 0.54 | **0.70** |
| phi4:14b | 0.71 | 0.65 | 0.63 | 0.64 |
| qwen3:14b (incumbent) | 0.64 | 0.68 | 0.63 | 0.65 |
| phi4-reasoning | 0.58 | 0.56 | 0.38 | 0.45 |
| gemma3:12b | 0.40 | 0.58 | 0.63 | 0.60 |

gpt-oss-safeguard:latest **shipped as Stage 4b's verifier** (env var `STAGE4B_MODEL` in `pipeline/stage4b_verify.py`). Other LLM stages still use qwen3 via `OLLAMA_MODEL`. **Implementation note**: the model is incompatible with Ollama's `format=schema` enforcement (zero response tokens when GBNF grammar is applied) — Stage 4b omits the format field and relies on the model's reliable native JSON output (0/100 parse failures on the gold set) plus post-hoc enum + quote validation.

Operational tradeoff: the carrier list is shorter (full Stage 4b run produced 90 verdicts / 67 articles vs qwen3's 198 / 138 on the same Stage 4a candidates) but every flag is reliable. Recall ~0.54 means ~46% of real carriers in the corpus are missed; for published findings, conservative (high-precision) is the right bias.

### Gold-set baseline drift — quantified, gold set rebuilt

The original 100-row gold set (`data/gold_set_labeled.csv`, 2026-04-28) was built against `stage4b_verdicts.json` and reported 90.0% overall accuracy, 0.84 carrier precision, 1.00 carrier recall. Despite the verdicts file remaining 95.5% unchanged on disk, fresh `verify()` calls on the same inputs began producing only ~50-56% agreement with the recorded verdicts (regardless of `think on/off`, `format=schema on/off`, `num_predict 600/1500/4000`).

The qwen3:14b model file on bigdoggie has mtime 2026-03-01 (well before the gold-set run) and is loaded fully on GPU at 14.9 GB VRAM. Ollama is at 0.17.1. Plausible drift causes — Ollama internal change (sampler/batching/KV-cache), some bigdoggie-side configuration change — are not bisectable from this side without version pins we don't have.

**Resolved by full rebuild** (2026-05-01):
1. ✅ Re-ran the full pipeline (Stage 0 → Stage 4b) end-to-end on the current corpus. New `stage4b_verdicts.json`: 1,763 verdicts (vs prior 3,220), 198 carriers across 138 articles (vs prior 315/136). Carrier overlap with prior run: only 77 articles (45% churn) — same model + similar inputs, materially different outputs.
2. ✅ Built fresh gold-set template (`data/gold_set_template_v2.csv`) sampling from new verdicts.
3. ✅ Re-judged with claude-opus-4-7 via `pipeline/gold_set_cloud_label.py` → `data/gold_set_labeled_v2.csv`.
4. ✅ Re-measured: **overall accuracy 65.0%, carrier precision 0.64, carrier recall 0.67** (vs historical 90% / 0.84 / 1.00).

The 0.64/0.67 numbers are the real current performance. The gold set is now ready for benchmarking candidate replacement models (see `docs/local_llm_accuracy_research.md`).

### Stage 4b structural-output enforcement — **SHIPPED**

Both `pipeline/claim_normalizer.py` (Stage 3.5) and `pipeline/stage4b_verify.py` (Stage 4b) now pass an Ollama JSON Schema as the `format` parameter. Token-level grammar-constrained generation guarantees the response parses as valid JSON matching the schema; Stage 4b's `verdict` field is constrained to the four-value `enum`. Eliminates the prose-summary regression mode (Stage 3.5) and structurally impossible to return invalid verdict strings (Stage 4b).

### Stage 4b evidence_quote hallucination — **SHIPPED + retroactively cleaned**

Audit on the 315 carrying verdicts found 91 (29%) had `evidence_quote` values that were not literal substrings of the article body — 66 pure paraphrases, 25 stitched abridgments. `quote_in_article()` validator added to `pipeline/stage4b_verify.py` auto-nulls hallucinations on future runs. `pipeline/stage4b_quote_reextract.py` ran a one-shot retroactive cleanup with a strict-literal prompt + the validator + 1 retry: 79/91 (87%) recovered as verifiable literal quotes, 12/91 (13%) honestly nulled. Post-cleanup hallucination rate: 0%.

Attempt to bake the strict-literal prompt into the main `verify()` (so quotes would be correct at generation time) regressed verdict accuracy 92% → 44% on the gold set — see "Stage 4b carrier-precision improvement attempts" below for details. Reverted. The post-hoc validator + retroactive reextract remain the right approach.

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
