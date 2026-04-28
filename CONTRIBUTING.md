# Contributing

This is a research project — the pipeline runs end-to-end on a single GPU host and produces a curated misinformation-carrier list as its main output. Most contributions will be one of:

1. **Bug reports**: open an issue with the pipeline stage, the input data shape, and the error or wrong output. If it's an LLM-output bug, include the `evidence_quote` / `verdict` / `reasoning` so we can reproduce.
2. **Pipeline / model improvements**: see `docs/BACKLOG.md` for the open work and `docs/local_llm_accuracy_research.md` for the research-track agenda. The biggest open question is the carrier-precision ceiling on local LLMs — see the research doc for candidates.
3. **Ideology-tag corrections**: `pipeline/source_ideology_tagger.py` contains `IDEOLOGY_MAP`. If you spot an outlet tagged wrong, open a PR with a one-line justification (e.g., AllSides or Ad Fontes link).

## Before opening a PR

- Run `python -m py_compile pipeline/*.py` to confirm everything compiles.
- If you touched a Stage 4b prompt or the LLM call shape, re-run `python pipeline/gold_set_eval.py` against `data/gold_set_labeled.csv` and report the precision/recall delta in the PR description. Prompt changes can regress carrier recall sharply (see the `## Failed mitigation attempts` section in `docs/local_llm_accuracy_research.md` for two cautionary examples).
- Match the existing code style — no formatter is enforced; keep imports tidy and avoid drive-by reformatting.

## Data and outputs

All pipeline outputs live in `data/` and are gitignored. Don't commit CSVs, JSONs, embedding `.npy` files, or logs from your runs. The `docs/FINDINGS.md` file is the regenerated reviewer report and is the only data-side artifact tracked in git.

## Setup recap

Setup is in `README.md`. Ollama-specific configuration is in `docs/ollama_setup.md`. Project conventions and gotchas live in `CLAUDE.md` (originally written for AI coding assistants, but useful as an operations reference for human contributors too).

## Reporting security or sensitive issues

For anything you'd rather not file publicly (a leaked credential, a sensitive misinformation finding that needs careful disclosure), email the maintainer rather than opening an issue.
