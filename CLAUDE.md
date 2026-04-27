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
- **Stage 4b UNKNOWN parse failures**: ~20% of verifier calls return `UNKNOWN` because qwen3 burns through `num_predict` on a `<think>` block despite the `/no_think` directive in the prompt. The verifier currently uses `num_predict=1500` after a recovery pass demonstrated 80%+ of UNKNOWNs are recoverable at the higher budget. If you see `UNKNOWN` rates >5% in a fresh run, the recovery pattern is: drop UNKNOWN rows from `data/stage4b_verdicts.json` and re-run `pipeline/stage4b_verify.py` (the resume logic will fill them back in). Carrier counts roughly doubled in the corpus run after this recovery (51 → 117).
- **Stage 3.5 normalizer fragility**: `pipeline/claim_normalizer.py` makes ONE big LLM call to cluster all claims at once. With ≥150 input claims at `num_ctx=8192`, qwen3 sometimes returns prose/markdown summaries instead of JSON. Stage 4a's fallback path (when `data/claim_families_filtered.json` is missing) reads `data/claims_verified.json` directly, so a normalizer failure doesn't break the pipeline — it just gives narrower retrieval. The proper fix (deferred) is to chunk the claims into batches of ~40 and merge family clusters via fuzzy matching of canonical claim texts.
- **Stage 4a embedding resilience**: chunks longer than nomic-embed-text's 2048 tokens or empty strings cause `400 Bad Request`. The script now truncates each chunk to 1500 words and falls back to single-item embed calls on batch failure (filling failed items with zero vectors so they never match). No manual chunk cleanup needed.

## Performance baselines (for sanity-checking re-runs)

Measured on bigdoggie RTX 4080 with `qwen3:14b` Q4_K_M, `num_ctx=8192`, `OLLAMA_NUM_PARALLEL=4`, 4 client workers:

| Stage | Throughput |
|---|---|
| Stage 1 classifier | ~0.4-0.5 rows/s (~9 s/row per worker) |
| Stage 2 claim extractor | ~0.05-0.07 rows/s (~15-20 s/row per worker; longer prompts/outputs) |
| Stage 4a embedding | full corpus in ~1 min (CPU/network-bound, not GPU) |
| Stage 4b verification | ~0.15-0.2 pairs/s |

If actual rates are >2× slower, the most likely cause is VRAM spill (see "VRAM math" gotcha) or partial GPU offload (see "GPU stranding").

## Git hygiene

- GitHub: `github.com/rickramos1/ai-media-analysis-tool`
- Main branch: `main`
- Windows→Linux clones may show phantom CRLF diffs on first clone. Fix once with `git config core.autocrlf input && git reset --hard`.
- `.gitignore` excludes all pipeline data outputs (CSVs, JSONs, .npy embeddings, .log files, *.bak.* archives). When in doubt, check it before adding new file types.
