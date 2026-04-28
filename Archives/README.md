# Archives

Older / superseded scripts and small smoke-test outputs from earlier iterations of this project. Kept for reference only — none of these are part of the current pipeline. Read them to understand how things evolved, but don't import or run them as part of normal use.

## Contents

| File | What it was |
|---|---|
| `main.py` | Smoke-test entry that called `utils/media_utils.find_sources_by_name()` to verify the MediaCloud connection |
| `test_connection.py` | Earlier MediaCloud connectivity check |
| `test_query.py` | Single-query smoke test against MediaCloud v4 |
| `queries_v1.py` | First version of MediaCloud topic queries; superseded by `pipeline/queries_public_collection_womens_health.py` |
| `queries_updated.py` | Second iteration of the same |
| `queries_public_collection.py` | Third iteration; the current production version is in `pipeline/` |
| `timeseries.py`, `timeseries_tracker.py` | Daily-counts time-series fetch experiments using the legacy MediaCloud API |
| `create_issues.py` | One-off helper that opened GitHub issues from a CSV (uses `GITHUB_TOKEN` from env) |
| `*.csv` | Smoke-test outputs from the scripts above. All under 1 KB; not real corpus data. |

## Note on secrets

These scripts read API keys from environment variables (`MEDIACLOUD_API_KEY`, `NEWS_API_KEY`, `GITHUB_TOKEN`). None of them have hardcoded credentials — but if you re-run them, you'll need those keys in your `.env`.

## Vestigial dependency

`Archives/main.py` is the only file outside `Archives/` that imports `utils/media_utils.py`. If you remove `Archives/`, you can also remove `utils/`.
