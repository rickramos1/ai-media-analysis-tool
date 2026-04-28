# ai-media-analysis-tool — Claude context

Pipeline that analyzes US media coverage of women's health topics for misinformation. See `README.md` for the user-facing overview and `docs/BACKLOG.md` for the cross-reference architecture spec. This file is for Claude/automation — project conventions, gotchas, operational context.

## Home machine

Canonical clone lives on the Ubuntu server (`gingerbean` / `netmaker-server`) at `~/projects/ai_media_analysis_tool/`. Runs there because the pipeline reaches out to a remote Ollama on `bigdoggie` (Windows host with the GPU), and scrapes benefit from the server's always-on uptime. The old Google Drive working copy at `G:\My Drive\_data_projects\mediacloud_tool\ai_media_analysis_tool\` is deprecated — treat it as a backup, not a clone.

## Repo layout

```
pipeline/    Stage scripts (Stage 0 → 5) + config.py + shared helpers in misinfo_detector.py
analysis/    One-off / non-pipeline analyses (e.g. keyword_analysis.py)
utils/       MediaCloud v4 client wrappers (vestigial — only Archives/main.py imports it)
data/        All pipeline data outputs — gitignored. Subdirs: backups/, logs/, archive/
docs/        BACKLOG.md, FINDINGS.md (regenerated), narrative_clusters.md, pbi_build_guide.md
groups/      Source-group JSONs for ideology-bucket queries
Archives/    Older / superseded scripts and data — read for reference, don't modify
```

All scripts run from project root (e.g. `python -u pipeline/article_classifier.py`). Python adds the script's own directory to `sys.path` so sibling imports inside `pipeline/` (`from misinfo_detector import ...`) work without a package layout. Don't `cd pipeline` to run — data paths are written relative to root (`data/...`).

## Pipeline

```
pipeline/queries_public_collection_womens_health.py     →  data/womens_health_articles.csv
pipeline/scrape_article_text.py                         →  data/womens_health_articles_text.csv
pipeline/misinfo_detector.preprocess_csv                →  data/womens_health_articles_text_clean.csv
pipeline/article_classifier.py        (Stage 1, LLM)    →  data/articles_classified.csv
pipeline/claim_extractor.py           (Stage 2, LLM)    →  data/claims.json
pipeline/stage3_filter.py             (Stage 3)         →  data/claims_verified.json + data/claims_all_with_ideology.json
pipeline/claim_normalizer.py          (Stage 3.5, LLM)  →  data/claim_families.json + data/claim_families_filtered.json
pipeline/stage4a_retrieval.py         (Stage 4a, embed) →  data/stage4a_candidates.json + data/embeddings_*.npy
pipeline/stage4b_verify.py            (Stage 4b, LLM)   →  data/stage4b_verdicts.json + data/misinfo_carriers.csv
pipeline/stage5_report.py             (Stage 5)         →  data/misinfo_carriers_by_article.csv + docs/FINDINGS.md
analysis/keyword_analysis.py                            →  data/keyword_trends.csv, data/keyword_trends.png
pipeline/source_ideology_tagger.py                      →  tagged output (paths via --infile/--outfile)
```

### Optional supporting tools

```
pipeline/external_factchecks.py     →  data/external_factchecks_claims.json
    Pulls debunked-claim records from the Google Fact Check Tools API
    (women's-health filtered) in claims.json shape. Re-run Stage 3 with
    `--extra-input data/external_factchecks_claims.json` to merge them
    into the canonical-claim universe. Requires GOOGLE_FACTCHECK_API_KEY
    in .env.

pipeline/gold_set_build.py          →  data/gold_set_template.csv
pipeline/gold_set_eval.py           →  data/gold_set_metrics.json
    Stratified Stage 4b precision harness. `gold_set_build.py` samples
    pairs from data/stage4b_verdicts.json into a labelable CSV (default
    25 per verdict class, 100 total). Reviewer fills `human_verdict`
    (or `cloud_llm_verdict` if Claude is the judge — `gold_set_eval.py`
    auto-detects either column or override via `--judge-col`/`--llm-col`),
    saves as data/gold_set_labeled.csv. Eval prints a confusion matrix,
    per-class precision/recall/F1, and carrier FP/FN listings. Most recent
    measurement: carrier precision 0.84, recall 1.00, accuracy 0.90.

pipeline/gold_set_reverify.py
    Targeted re-verification helper. Runs Stage 4b's verify() against the
    100 gold-set pair_ids only and writes a new `ollama_verdict_v2` column
    so prompt/model changes can be benchmarked against the same labels
    without a full Stage 4b rerun. Has known limitation: pair_ids built
    pre-audit may not match current verdicts file; affected rows are
    reported as misses.

pipeline/stage4b_quote_reextract.py
    Re-extracts evidence_quote for carrying verdicts whose original quote
    is not a literal substring of the article body. Strict prompt + Ollama
    format= schema + substring validator + 1 retry on hallucination.
    Reduced the carrier-pool hallucination rate from 29% (91/315) to 0%
    in one pass (87% recovery, 13% honestly nulled).

pipeline/stage4b_refute_check.py
    Post-processing refutation-detection pass on carrying verdicts.
    SHIPPED BUT EMPIRICALLY UNSUITABLE for qwen3:14b — see
    docs/local_llm_accuracy_research.md §"Failed mitigation attempts."
    Hand-audit found ~57% wrong demotions (qwen3 routinely treats supportive
    citations as refutations). Preserved for re-testing against candidate
    replacement models from the research project.
```

`run_pipeline_1_to_4a.sh` orchestrates stages 1 → 4a end-to-end. Stage 4b is run separately because it's the longest LLM stage and the user wants explicit GPU windows for it.

**Final reviewer outputs** are `data/misinfo_carriers_by_article.csv` (one row per unique flagged article) and `docs/FINDINGS.md` (human-readable report). Generate both with `pipeline/stage5_report.py`. The campaigns table's `Description` column is the representative carried claim text per actor; the editorial prose that appeared in earlier runs (refutation context, policy framing) can be hand-polished after regen if desired.

**Power BI handoff**: `data/misinfo_carriers_pbi.csv` (enriched with outlet ideology + publish date) and `data/stage4b_all_verdicts_pbi.csv` (full verdict set, used for rate measures) are the data files. `docs/pbi_build_guide.md` walks the team through the one-time .pbix build in Power BI Desktop on Windows. After subsequent pipeline reruns, regenerated CSVs drop into the same folder and the team clicks **Refresh** in PBI — no rebuild needed.

Run from the project root with the venv activated. `pipeline/misinfo_detector.py` and the LLM stages support `--max-rows N` (or smoke-test patterns) — use them before a full run.

The first-pass `pipeline/misinfo_detector.py` pre-dates the cross-reference pipeline. It still ships shared helpers (`filter_eligible`, `format_hms`, `TOPIC_TERMS`, `CONTEXT_RX`) that the new stages import. Don't delete it without porting those helpers.

## Environment

- **Python**: 3.12 on the server (native venv in `.venv/`). Rebuild after machine migration; never copy across platforms.
- **Dependencies**: pinned loosely in `requirements.txt`. `pandas>=3.0.0` is intentional. Required: `trafilatura`, `rapidfuzz`, `brotli` (the last is non-obvious — see "Brotli" gotcha below).
- **MediaCloud API key** lives in `.env` (never committed). If missing, the user regenerates at mediacloud.org.
- **Ollama** is required for stages 1, 2, 3.5, 4a, 4b. The pipeline talks to a remote Ollama on `bigdoggie` (`http://192.168.86.24:11434`) — see `memory/remote_ollama.md` for the rationale and configuration. `OLLAMA_HOST`, `OLLAMA_MODEL` (default `qwen3:14b`), `OLLAMA_EMBED_MODEL` (default `nomic-embed-text`), `OLLAMA_PARALLEL` (default 4 in pipeline scripts) all read from `.env`.

## Data files

All CSVs, pipeline JSONs, .npy embeddings, manifests, logs, and backups live under `data/` and are gitignored. Don't commit. If asked to "clean up", confirm before deleting; the scrape is HTTP-bound and slow, the LLM stages take ~1-2 hours each. The Power BI `.pbix` was Windows-only and has been removed from the server copy.

`data/backups/*.bak.YYYYMMDD` files are created when archiving prior pipeline outputs before re-runs (also gitignored). They're safe to delete once you're confident the new run is correct. `data/archive/` holds stale outputs from superseded runs (pre-cross-reference pipeline, old keyword analysis); also safe to delete.

## Conventions

- Scripts are standalone — each can be run independently given upstream outputs exist.
- LLM stages support **incremental checkpointing**: on restart, they read the prior output and skip rows already done. Use this — the run can be killed safely and resumed.
- No test suite yet. If you add tests, put them in `tests/` and wire up `pytest`.
- `Archives/` holds older iterations — read for reference, don't modify without asking.
- When unsure about MediaCloud API shape, check `utils/media_utils.py` — it centralizes v4 client usage.
- For non-trivial pipeline changes, update `docs/BACKLOG.md` if you defer something, and reflect it in this file's pipeline diagram.

## Known constraints + gotchas

- **VRAM math on bigdoggie**: 16 GB RTX 4080 + `qwen3:14b` (~12 GB weights) means KV cache slots eat the rest. `OLLAMA_NUM_PARALLEL=4` (the bigdoggie default that the tray app re-asserts on every login) only fits if our client requests `num_ctx ≤ ~8192`. The pipeline scripts (`article_classifier.py`, `claim_extractor.py`, `stage4b_verify.py`) default to `num_ctx=8192` for this reason. If you bump it back to 16384 you'll spill to CPU and run ~6× slower.
- **GPU stranding**: if any other process held the GPU when `qwen3:14b` first loaded, Ollama silently runs the model on CPU and stays there. Symptom: `/api/ps` shows `size_vram: 0`. Fix: `POST /api/generate {"model":"qwen3:14b","keep_alive":0}` to unload, then send any prompt to reload onto GPU. See `memory/remote_ollama.md`.
- **Brotli decompression**: the scraper advertises `Accept-Encoding: gzip, deflate, br`. Without the `brotli` Python package installed, brotli-encoded responses come back as unparseable bytes and trafilatura returns 0 chars (silent ~50% data loss across the corpus). `brotli>=1.1.0` is in `requirements.txt`; verify it's installed before re-scraping.
- **MediaCloud v4 API instability**: queries occasionally return empty JSON ("Expecting value: line 1 column 1 (char 0)"). The query script retries 3× and moves on; if a topic finishes short, re-run just that topic.
- **WAF/Cloudflare blocks**: UA rotation + realistic headers gets past static heuristics. Cloudflare-tier blocks (Newsweek, Forbes, ABC News, parts of WaPo) still 403. Next tier is `curl_cffi` (TLS fingerprint) or `playwright` (real browser); not yet implemented.
- **Topic gate (hybrid)**: `misinfo_detector.filter_eligible` admits `passes_wc AND (regex_pass OR semantic_score ≥ SEMANTIC_GATE_THRESHOLD) AND is_canonical`. The regex side reads `TOPIC_TERMS`; the semantic side reads `data/article_topic_scores.csv` (produced by `pipeline/semantic_topic_gate.py`); the dedupe side reads `data/article_dedup_map.csv` (produced by `pipeline/dedupe_articles.py`) joined on `(url, topic)`. Default threshold 0.70, override via env `SEMANTIC_GATE_THRESHOLD`. **`TOPIC_TERMS` is no longer load-bearing on its own** — when you change `queries_public_collection_womens_health.py`, you can either update `TOPIC_TERMS` or rely on the semantic gate (re-run `semantic_topic_gate.py` to refresh scores against the new query set). For shadow-style regex-only comparisons pass `hybrid=False`.
- **Off-topic claim contamination**: broad fact-check articles (factcheck.org weekly roundups) extract claims unrelated to women's health (Medicaid, COVID, ADHD, weight-loss drugs). The Stage 3.5 `claim_normalizer.py` includes a `WOMENS_HEALTH_RX` filter that drops these from the family list. Verify the filter still catches the new contamination patterns when corpus changes.
- **`OLLAMA_LLM_LIBRARY=cuda_v12` keeps reverting** on bigdoggie (the tray app re-asserts it). If the pipeline mysteriously slows, check `/api/ps` and that the model is fully on GPU — but the pipeline's own settings are robust to either CUDA library version. Don't fight this unless something else is broken.
- **qwen3 `/no_think` is silently ignored** — the model emits `<think>...</think>` tokens that consume the entire `num_predict` budget, leaving `response: ""` with `done_reason: "length"`. The proper fix is Ollama's native reasoning toggle: pass `"think": false` at the top level of the `/api/generate` payload (NOT inside `options`). Confirmed working on Ollama 0.17.1 with qwen3:14b. **All five LLM-using scripts now pass `"think": false`** (`article_classifier.py`, `claim_extractor.py`, `claim_normalizer.py`, `stage4b_verify.py`, `misinfo_detector.py`). The `/no_think` directive remains at the top of each prompt as belt-and-suspenders but is the API toggle that's load-bearing.
- **Stage 4b UNKNOWN parse failures (legacy mitigation)**: ~20% of verifier calls used to return `UNKNOWN` because of the `/no_think`-ignored issue. Mitigated historically by `num_predict=1500` (post-recovery rate was 0.4%, 9/2,147). With `"think": false` now applied, the budget bump is no longer load-bearing — `num_predict` could be dropped back to ~400 to speed up Stage 4b further. Recovery pattern if `UNKNOWN` rate spikes: drop UNKNOWN rows from `data/stage4b_verdicts.json` and re-run `pipeline/stage4b_verify.py` (resume logic fills them back in).
- **Stage 3.5 normalizer**: `pipeline/claim_normalizer.py` chunks the input into batches of `--chunk-size` (default 40) and merges per-batch families across batches by fuzzy-matching `canonical_claim` text (rapidfuzz `token_set_ratio ≥ 80`, same threshold as Stage 3 source-name normalization). Per-batch parse failures degrade gracefully — claims become singleton families instead of being lost to a whole-run failure. The earlier single-LLM-call design returned prose summaries above ~150 input claims at `num_ctx=8192`; chunking eliminates that fragility. Stage 4a's fallback path (when `data/claim_families_filtered.json` is missing) reads `data/claims_verified.json` directly — preserved as a safety net but no longer routinely triggered.
- **Ollama `format=` schema enforcement on Stage 3.5 + Stage 4b**: both scripts pass a JSON Schema as the `format` parameter on `/api/generate`. Ollama's GBNF-grammar layer constrains generation at the token level so the response is guaranteed to parse as JSON matching the schema. Stage 4b's `verdict` field is constrained to the four-value `enum`, so invalid verdict strings are now structurally impossible. Ships as a separate gotcha because the failure modes it eliminates (Stage 3.5 prose-summary regressions, Stage 4b UNKNOWN parses) used to dominate the engineering work.
- **Evidence quote substring validator (Stage 4b)**: after every Stage 4b call, `quote_in_article()` checks whether the LLM's `evidence_quote` is a literal substring of the article body (whitespace + smart-quote normalized, ≥12 char threshold). If the quote can't be found, it's nulled and `evidence_quote_hallucinated: true` is set on the verdict. Audit on the original 315 carrying verdicts found 91 (29%) hallucinated quotes — pure paraphrases or stitched abridgments. `pipeline/stage4b_quote_reextract.py` ran a one-pass cleanup with a strict-literal prompt + the validator + 1 retry, recovering 79 (87%) as verifiable literal quotes and honestly nulling the remaining 12. Post-cleanup hallucination rate: 0%. The strict-literal prompt is not yet in the main verifier — adding it would prevent hallucinations at generation time instead of catching them post-hoc.
- **Stage 4a embedding resilience**: chunks longer than nomic-embed-text's 2048 tokens or empty strings cause `400 Bad Request`. The script now truncates each chunk to 1500 words and falls back to single-item embed calls on batch failure (filling failed items with zero vectors so they never match). No manual chunk cleanup needed.

## Performance baselines (for sanity-checking re-runs)

Measured on bigdoggie RTX 4080 with `qwen3:14b` Q4_K_M, `num_ctx=8192`, `OLLAMA_NUM_PARALLEL=4`, 4 client workers:

| Stage | Throughput |
|---|---|
| Stage 1 classifier | ~0.4-0.5 rows/s (~9 s/row per worker) — pre-`think: false` baseline; smoke test post-toggle showed ~0.7s/call |
| Stage 2 claim extractor | ~0.05-0.07 rows/s (~15-20 s/row per worker; longer prompts/outputs) — pre-`think: false` baseline |
| Stage 4a embedding | full corpus in ~1 min (CPU/network-bound, not GPU) |
| Stage 4b verification | ~0.15-0.2 pairs/s — pre-`think: false` baseline |

The Stage 1/2/4b numbers above are from before `"think": false` was applied across all LLM stages (~5× of wall time on each LLM stage was reasoning-token generation that was discarded). Re-measure after the next full pipeline run; expect substantial speedup.

If actual rates are >2× slower, the most likely cause is VRAM spill (see "VRAM math" gotcha) or partial GPU offload (see "GPU stranding").

## Git hygiene

- GitHub: `github.com/rickramos1/ai-media-analysis-tool`
- Main branch: `main`
- Windows→Linux clones may show phantom CRLF diffs on first clone. Fix once with `git config core.autocrlf input && git reset --hard`.
- `.gitignore` excludes all pipeline data outputs (CSVs, JSONs, .npy embeddings, .log files, *.bak.* archives). When in doubt, check it before adding new file types.
