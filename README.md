# AI Media Analysis Tool

Analyzes US media coverage of women's health topics for misinformation. Uses [MediaCloud](https://mediacloud.org/) to gather articles, then runs a multi-stage pipeline that distinguishes fact-checking journalism from misinfo carriers and cross-references claims against an ideology-weighted, multi-outlet-corroborated database of debunked claims.

## What It Does

1. **Collects articles** from MediaCloud across 10 carrier-focused topic queries (abortion-pill reversal, chemical-abortion harm framing, EC-as-abortifacient, IUD misinfo, mifepristone safety attacks, fertility-awareness superiority, CPC promotion, trad-wife anti-contraception, wellness-influencer hormone misinfo, generalized birth-control harm claims).
2. **Scrapes full article text** with `trafilatura` (drops nav/footer/sponsor blurbs) and rotated human-browser headers.
3. **Classifies each article** as `FACT_CHECK`, `ORIGINAL`, or `OTHER` (Stage 1).
4. **Extracts debunked claims** from FACT_CHECK articles — claim text, originating actor, refutation, evidence sources (Stage 2).
5. **Filters claims** by ideology cross-reference: requires either ≥2 different ideology buckets debunking the claim, *or* a single authoritative-solo outlet (Stage 3).
6. **Normalizes** raw claim texts into canonical claim families (Stage 3.5), then drops off-topic contamination from broad fact-check roundups.
7. **Retrieves candidate carriers** for each verified claim against ORIGINAL articles via `nomic-embed-text` cosine similarity (Stage 4a).
8. **Verifies carriers** with the LLM: classifies each candidate article-claim pair as `carrying`, `debunking`, `neutral_reporting`, or `irrelevant` (Stage 4b).
9. **Tags sources by ideology** for downstream analysis.

The pipeline is built around a "best-data" / zero-hallucination posture — `temperature=0`, allowed-abstention output (`Unknown`), and human-auditable provenance for every flagged article.

## Setup

```bash
# Create virtual environment
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Install mediacloud from GitHub (if pip install fails)
pip install git+https://github.com/mediacloud/api-client.git

# Configure API key
# Create a .env file with:
# MEDIACLOUD_API_KEY=your_key_here
# OLLAMA_HOST=http://<your-ollama-host>:11434
# OLLAMA_MODEL=qwen3:14b
```

### Ollama

The pipeline uses Ollama for both `qwen3:14b` (classification, claim extraction, verification) and `nomic-embed-text` (Stage 4a vectorization).

Install on the GPU host:

```bash
ollama pull qwen3:14b
ollama pull nomic-embed-text
```

To run Ollama on a different machine (recommended — the pipeline GPU is the bottleneck), set in `.env`:

```bash
OLLAMA_HOST=http://<remote-host>:11434
OLLAMA_MODEL=qwen3:14b
```

The remote daemon must bind a non-loopback interface. Start it with `OLLAMA_HOST=0.0.0.0:11434 ollama serve` and ensure port 11434 is reachable.

VRAM math matters. On a 16 GB GPU running `qwen3:14b` (Q4_K_M, ~12 GB weights), the server's `OLLAMA_NUM_PARALLEL` and the client's per-request `num_ctx` interact:

| `NUM_PARALLEL` | Per-slot KV at 16 k ctx | Total VRAM |
|---|---|---|
| 2 | 1.4 GB × 2 = 2.8 GB | 14.8 GB ✅ |
| 4 | 1.4 GB × 4 = 5.6 GB | 17.6 GB ❌ (CPU spill) |
| 4, with `num_ctx=8192` (default in pipeline) | 0.7 GB × 4 = 2.8 GB | 14.8 GB ✅ |

The pipeline scripts default to `num_ctx=8192` so they coexist with `NUM_PARALLEL=4` without spilling.

## Pipeline

Run scripts in order. Each is idempotent — re-running picks up from checkpoints where applicable.

```bash
# 1. Query MediaCloud (10 carrier-focused topic queries)
python queries_public_collection_womens_health.py

# 2. Scrape full text (trafilatura, UA rotation, brotli)
python scrape_article_text.py

# 3-7: Cross-reference misinfo pipeline (or use the orchestrator below)
./run_pipeline_1_to_4a.sh   # runs preprocess + stages 1, 2, 3, 3.5, 4a
python stage4b_verify.py    # Stage 4b — run when GPU is available

# Optional: keyword trends + ideology tagging
python keyword_analysis.py
python source_ideology_tagger.py --infile womens_health_articles_text.csv --outfile tagged_output.csv
```

## Output Files

| File | Stage | Description |
|---|---|---|
| `womens_health_articles.csv` | Query | MediaCloud article metadata |
| `womens_health_articles_text.csv` | Scrape | + scraped `full_text` |
| `womens_health_articles_text_clean.csv` | Preprocess | malformed-row filter |
| `articles_classified.csv` | 1 | + `article_type` (FACT_CHECK / ORIGINAL / OTHER), `classifier_reason` |
| `claims.json` | 2 | claims debunked in each FACT_CHECK article |
| `claims_all_with_ideology.json` | 3 | normalized claim sources + outlet ideologies |
| `claims_verified.json` | 3 | claims passing the ideology cross-reference |
| `claim_families.json` / `claim_families_filtered.json` | 3.5 | canonical claim families (full + women's-health filtered) |
| `embeddings_article_chunks.npy` / `embeddings_claims.npy` | 4a | persisted 768-dim vectors (reusable for clustering / dedup) |
| `stage4a_candidates.json` | 4a | top-K claim matches per article + global top pairs |
| `stage4b_verdicts.json` | 4b | per-pair LLM verdicts |
| `misinfo_carriers.csv` | 4b | final flagged carriers (one row per `carrying` verdict) |
| `misinfo_carriers_by_article.csv` | (post) | one row per unique flagged article; multiple claims collected in `claims_carried_json` |
| `FINDINGS.md` | (post) | human-readable summary report — methodology, top campaigns, top flagged articles, honest limits, reviewer workflow |
| `misinfo_carriers_pbi.csv` | (post) | Power BI-ready carriers data, enriched with outlet ideology + publish date |
| `stage4b_all_verdicts_pbi.csv` | (post) | full verdict set for PBI rate/proportion measures |
| `pbi_build_guide.md` | (post) | step-by-step Windows-side guide for building the dashboard .pbix |
| `keyword_trends.csv` / `keyword_trends.png` | (optional) | weekly keyword frequency |

## Project Structure

```
config.py                                    # MediaCloud API client
queries_public_collection_womens_health.py   # MediaCloud queries (carrier-focused)
scrape_article_text.py                       # Trafilatura + UA rotation
misinfo_detector.py                          # First-pass detector + shared filter helpers
article_classifier.py                        # Stage 1: FACT_CHECK / ORIGINAL / OTHER
claim_extractor.py                           # Stage 2: structured claim extraction
stage3_filter.py                             # Stage 3: ideology + auth-solo cross-reference
claim_normalizer.py                          # Stage 3.5: cluster claims into families
stage4a_retrieval.py                         # Stage 4a: embed + cosine retrieve
stage4b_verify.py                            # Stage 4b: LLM verification
run_pipeline_1_to_4a.sh                      # Orchestrator for stages 1 → 4a
keyword_analysis.py                          # (optional) keyword trends
source_ideology_tagger.py                    # Outlet ideology map (Right/Center/Left buckets)
BACKLOG.md                                   # Future work + architecture spec
groups/                                      # Media source group definitions
utils/media_utils.py                         # MediaCloud helpers
```

## APIs and Tools

- **MediaCloud API v4** — article search and metadata
- **Ollama** — local model serving
  - `qwen3:14b` — classification, claim extraction, verification
  - `nomic-embed-text` — Stage 4a vectorization
- **trafilatura** — article body extraction (drops nav/footer/sponsor)
- **rapidfuzz** — claim-source name normalization (Stage 3)
- **pandas / numpy** — data manipulation, similarity math

## Notes

- See `BACKLOG.md` for the cross-reference architecture spec, future iterations (DuckDB / GCP scalability, n-gram analysis, broader ideology coverage), and the rationale for the current design.
- Scraping respects publishers — UA rotation and randomized delays help with static bot heuristics but do not defeat Cloudflare-tier WAFs (Newsweek, Forbes, ABC News, parts of WaPo currently fail).
- All flagged articles in `misinfo_carriers.csv` carry full provenance: which claim was carried, which outlets debunked it, and the specific passage in the article that matched. Designed for human review before publication.
- After Stage 4b, run a small post-processing block (see most recent run notes) to generate `misinfo_carriers_by_article.csv` (one row per unique flagged article) and `FINDINGS.md` (a human-readable summary report with methodology, top campaigns, top flagged articles, honest limits, and a reviewer workflow). Hand `misinfo_carriers_by_article.csv` to reviewers; share `FINDINGS.md` with anyone reading the work.
- The verifier sometimes returns `UNKNOWN` because qwen3 enters `<think>` mode despite `/no_think`. After a full Stage 4b run, if `UNKNOWN` count is >5% of verdicts, drop those rows from `stage4b_verdicts.json` and re-run — the resume logic will fill them back in at the higher `num_predict=1500` budget. In the corpus run that produced the current outputs, this recovery pass roughly doubled the carrier count (51 → 117).
