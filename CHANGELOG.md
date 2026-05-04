# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-05-04

First public release. Local-LLM-based misinformation detection pipeline that
flags articles "carrying" previously-debunked health claims — i.e., articles
that present a fact-checked-false claim as true without acknowledging the
debunking. Cloud-LLM-validated carrier precision **0.978** on a 377-row gold
set; ~98% of flagged articles confirmed real carriers per a Claude Opus 4.7
judge.

### Pipeline

- **Stage 0 — preprocess**: MediaCloud query (`pipeline/queries_public_collection_womens_health.py`) → article scrape (`pipeline/scrape_article_text.py`) → topic gate (regex + semantic) + syndicated-coverage dedupe (`pipeline/misinfo_detector.py`).
- **Stage 1 — article classification** (qwen3:14b on local Ollama): `pipeline/article_classifier.py` labels each article as ORIGINAL, FACT_CHECK, or OTHER.
- **Stage 2 — claim extraction** (qwen3:14b): `pipeline/claim_extractor.py` extracts debunked claims from FACT_CHECK articles.
- **Stage 3 — ideology cross-reference**: `pipeline/stage3_filter.py` promotes claims to canonical when supported by multi-ideology debunks or authoritative-solo outlets. Accepts external claim sources via `--extra-input`.
- **Stage 3.5 — claim normalization** (qwen3:14b): `pipeline/claim_normalizer.py` clusters near-duplicate claims into canonical families; women's-health regex filter removes off-topic contamination.
- **Stage 4a — embedding retrieval** (nomic-embed-text): `pipeline/stage4a_retrieval.py` embeds articles + claims and emits top-K candidate pairs above a cosine similarity threshold.
- **Stage 4b — LLM verification** (gpt-oss-safeguard:latest): `pipeline/stage4b_verify.py` classifies each (article, claim) pair as `carrying`, `debunking`, `neutral_reporting`, or `irrelevant`. Includes a literal-substring evidence-quote validator.
- **Stage 5 — reports + exports**: `pipeline/stage5_report.py` produces `docs/FINDINGS.md`, `data/misinfo_carriers_by_article.csv`, and a per-pair `data/misinfo_carriers_spot_check.csv` for human review. `pipeline/stage5_pbi_export.py` produces Power BI input CSVs enriched with outlet ideology and publish date.

### Validation harness

- **Stratified gold-set sampling** (`pipeline/gold_set_build.py`): samples N pairs per verdict class from the production verdicts file.
- **Cloud-LLM judging** (`pipeline/gold_set_cloud_label.py`): calls the Anthropic API (Claude Opus 4.7 by default) to fill `cloud_llm_verdict` on the gold-set template. Concurrency 12, ~$15 for a 377-row set, ~3 min wall.
- **Multi-model bake-off** (`pipeline/gold_set_bakeoff.py`): runs N candidate Ollama models against the cloud-judged gold set in turn and prints per-model precision/recall/F1.
- **Per-model reverification** (`pipeline/gold_set_reverify.py`): runs `verify()` against the gold-set pair_ids only — for testing prompt or model changes without a full Stage 4b rerun.
- **Confusion matrix and per-class metrics** (`pipeline/gold_set_eval.py`).

### External claim source

- **Google Fact Check Tools API integration** (`pipeline/external_factchecks.py`): pulls debunked claims from IFCN-certified fact-checkers (PolitiFact, Snopes, AFP, FactCheck.org) that MediaCloud's "US National Top Online" collection underweights. Filters to false/misleading verdicts + women's-health-relevant claims. Outputs in the same shape as Stage 2's claims for direct merge via `Stage 3 --extra-input`.

### Verifier model swap (key release-blocking accuracy work)

- 5-model bake-off against a 100-row Claude-Opus-4.7-judged gold set. Results:
  - **gpt-oss-safeguard:latest** (chosen): accuracy 0.83, carrier precision 1.00, recall 0.54
  - phi4:14b: 0.71 / 0.65 / 0.63
  - qwen3:14b (incumbent): 0.64 / 0.68 / 0.625
  - phi4-reasoning: 0.58 / 0.56 / 0.38
  - gemma3:12b: 0.40 / 0.58 / 0.625
- gpt-oss-safeguard is incompatible with Ollama's `format=schema` enforcement (zero response tokens when GBNF grammar applied); Stage 4b drops the schema and relies on the model's native JSON + post-hoc enum validation (0/100 parse failures on the gold set).
- Validated on a 377-row gold set covering all 90 production carrier flags + 100 each of debunking/irrelevant + 87 neutral_reporting:
  - Carrier precision: **0.978** (88/90; 95% Wilson CI ~0.92–0.997, population-level)
  - Carrier recall: 0.599 (88/147; sampled, stratification-biased)
  - Overall accuracy: 0.751
- Other LLM stages (Stages 1, 2, 3.5) still use qwen3:14b via `OLLAMA_MODEL`; Stage 4b alone uses `STAGE4B_MODEL` (default `gpt-oss-safeguard:latest`).

### Quality safeguards

- **Topic gate (hybrid)**: `passes_wc AND (regex_pass OR semantic_score ≥ 0.65) AND is_canonical`. Semantic gate uses per-topic centroids built from the MediaCloud query text plus seed articles. Dedupe map collapses near-duplicate articles (cosine ≥ 0.95) so syndicated coverage doesn't inflate per-outlet counts.
- **Schema-constrained generation** (Stage 3.5 only — Stage 4b dropped after the model swap): Ollama's GBNF grammar enforcement guarantees JSON-shape outputs from qwen3:14b.
- **`"think": false`** passed to Ollama on every LLM call. The `/no_think` prompt directive is silently ignored by qwen3:14b; without the API toggle, the model exhausts the `num_predict` budget on a `<think>` block and returns empty.
- **Evidence-quote substring validator**: post-hoc validates each Stage 4b verdict's `evidence_quote` is a literal substring of the article body (whitespace + smart-quote normalized, ≥12-char threshold). If not, the quote is nulled and `evidence_quote_hallucinated: true` is set on the verdict.
- **Spot-check CSV**: human-review file (`data/misinfo_carriers_spot_check.csv`) with `spot_check_ok` and `notes` columns at the front for editorial QA before publishing carrier names.

### Tooling and docs

- `pipeline/cluster_articles.py`: emergent-narrative clustering on article embeddings → `docs/narrative_clusters.md`.
- `pipeline/stage4b_quote_reextract.py`: one-shot retroactive quote-hallucination cleanup with a strict-literal prompt + 1 retry.
- `pipeline/source_ideology_tagger.py`: hardcoded outlet → ideology map (Left / Center-Left / Center / Center-Right / Right).
- `docs/pbi_build_guide.md`: step-by-step Power BI dashboard build.
- `docs/SCOPE_EXPANSION_PLAN.md`: multi-domain expansion blueprint (elections, climate, war/foreign policy, immigration/crime).
- `CLAUDE.md`: agent-context document covering project conventions, gotchas, and known constraints.

### Privacy / data sovereignty

- **All LLM inference runs locally on Ollama**. No article content or claim text is sent to any LLM provider during the production pipeline (Stages 0–5).
- External services used only for non-inference work:
  - **MediaCloud API** — article discovery (search query terms + URLs/metadata returned).
  - **Google Fact Check Tools API** — optional claim seed (search query terms only).
  - **Anthropic API** — optional gold-set validation (article body + claim text for the sampled rows).

### Known limitations

- **Recall is bounded by the fact-check corpus.** The pipeline can only flag articles carrying claims a fact-checker in our corpus has already debunked. Novel misinfo not present in the fact-check set is invisible to it.
- **Cloudflare-tier WAFs** (Newsweek, Forbes, ABC News, parts of WaPo) still 403 the scraper. Static UA rotation + realistic headers clears static heuristics; the next tier is `curl_cffi` or `playwright` (deferred — see `docs/BACKLOG.md`).
- **Verifier accuracy** validated only on the women's-health domain. Generalization to other domains (elections, climate, war/foreign policy, immigration/crime) requires per-domain gold-set validation — see `docs/SCOPE_EXPANSION_PLAN.md`.
- **Gold-set baseline drift**: the original 2026-04-28 gold set (qwen3:14b, format=schema, reported 90% accuracy / 0.84 carrier precision) is no longer reproducible — same model file, same code, but ~50% agreement with the recorded verdicts now. The 2026-05-01 cloud-rebuild on a fresh end-to-end pipeline rerun is the current ground truth. Most plausible cause: an Ollama internal change (sampler/batching/KV-cache) between the original run and now.

### Ecosystem

- Local Ollama (`OLLAMA_HOST` in `.env`). Stage 4b uses `gpt-oss-safeguard:latest` (override via `STAGE4B_MODEL`); other LLM stages use `qwen3:14b` by default (override via `OLLAMA_MODEL`).
- Python 3.12 via `requirements.txt`. Anthropic SDK is optional (only required when running gold-set cloud labeling).
- LICENSE: see `LICENSE` file in the repo root.

---

## Pre-release history (commit-only, not formally versioned)

- **2026-05-04** (`2074ee6` Phase A.5): SRHR collection + 8-yr window + scope expansion plan. Corpus 1,486 → 3,065 raw articles, carrier articles 71 → 135.
- **2026-05-01** (`cdb3661` Stage 5): spot-check CSV + PBI exports + validation section in FINDINGS.
- **2026-05-01** (`d2f0643`): 377-row gold-set validation of gpt-oss-safeguard.
- **2026-05-01** (`e185de4`): model swap qwen3 → gpt-oss-safeguard for 1.00 carrier precision.
- **2026-04-28** (`22e4335`): public-release prep — LICENSE, generic Ollama config, doc cleanup.
- **2026-04-28** (`4bf89fb`): Stage 4b accuracy push — gold-set harness, structured outputs, evidence-quote validator + retroactive re-extract.
- **2026-04-27** (`385dfde`): reorg into `pipeline/`, `data/`, `docs/` subdirs; wire up hybrid topic gate and dedupe filter.
- **2026-04-23** (`fb3a2a3`, `8bf17a6`, `8bed559`, `a5b481a`, `103c977`, `297d64e`, `d1ab62c`): emergent-narrative clustering + scraper error-row bug fix; semantic topic gate + syndicated-coverage dedupe (shadow mode); Power BI build guide + PBI-ready CSV outputs; Stage 5 formalized as `stage5_report.py`; initial end-to-end pipeline run (117 carriers across 65 articles).
- **2026-04-18** (`6ba25e3`): cross-reference misinfo detection pipeline (Stages 1–4b) added.
- **2026-04-15** (`8886b6a`): initial agent-context (`CLAUDE.md`).
