# ai-media-analysis-tool — Claude context

Pipeline that analyzes US media coverage of women's health topics for misinformation. See `README.md` for the user-facing overview. This file is for Claude/automation — project conventions, gotchas, and operational context.

## Home machine

Canonical clone lives on the Ubuntu server (`gingerbean` / `netmaker-server`) at `~/projects/ai_media_analysis_tool/`. Runs there because step 3 needs a local Ollama, and scrapes benefit from the server's always-on uptime. The old Google Drive working copy at `G:\My Drive\_data_projects\mediacloud_tool\ai_media_analysis_tool\` is deprecated — treat it as a backup, not a clone.

## Pipeline

```
queries_public_collection_womens_health.py  →  womens_health_articles.csv
scrape_article_text.py                       →  womens_health_articles_text.csv (+ _clean)
misinfo_detector.py                          →  misinfo_flagged_output.csv
keyword_analysis.py                          →  keyword_trends.csv, keyword_trends.png
source_ideology_tagger.py                    →  tagged output
```

Run from the project root with the venv activated. `misinfo_detector.py` supports `--max-rows N` for smoke tests — always use it before a full run.

## Environment

- **Python**: 3.12 on the server (native venv in `.venv/`). Rebuild the venv after machine migration — never copy it across platforms.
- **Dependencies**: pinned loosely in `requirements.txt`. `pandas>=3.0.0` is intentional; don't downgrade.
- **MediaCloud API key** lives in `.env` (never committed). If missing, the user regenerates at mediacloud.org.
- **Ollama** is required for `misinfo_detector.py`. Install on the host (`curl -fsSL https://ollama.com/install.sh | sh`), then `ollama pull llama3.2`. The detector talks to Ollama on `http://localhost:11434` by default.

## Data files

CSVs in the repo root are pipeline outputs. They're gitignored — do not commit. If asked to "clean up", confirm before deleting; some are expensive to regenerate (scrape takes hours). The Power BI `.pbix` was Windows-only and has been removed from the server copy.

## Conventions

- Scripts are standalone — each can be run independently given upstream outputs exist.
- No test suite yet. If you add tests, put them in `tests/` and wire up `pytest`.
- `Archives/` holds older iterations — read for reference, don't modify without asking.
- When unsure about API shape, check `utils/media_utils.py` first — it centralizes MediaCloud v4 client usage.

## Known constraints

- MediaCloud v4 API is rate-limited. Scrapes should batch with delays (already done in `scrape_article_text.py`).
- Ollama on the server has limited RAM; keep `--max-rows` reasonable during active dev.
- The source ideology map in `source_ideology_tagger.py` was recently expanded (commit `f379522`) to 68 sources / 85% coverage; verify coverage when adding new outlets.

## Git hygiene

- GitHub: `github.com/rickramos1/ai-media-analysis-tool`
- Main branch: `main`
- Windows→Linux clones may show phantom CRLF diffs on first clone. Fix once with `git config core.autocrlf input && git reset --hard`.
