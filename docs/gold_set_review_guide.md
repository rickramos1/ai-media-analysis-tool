# Stage 4b Gold-Set Labeling Guide

How to fill in `data/gold_set_template.csv` so `pipeline/gold_set_eval.py` can produce a precision/recall number for the Stage 4b LLM verifier.

## What this measures

For each `(article, claim)` pair Stage 4b returned a verdict — `carrying`, `debunking`, `neutral_reporting`, or `irrelevant`. We don't know how often those verdicts are correct. A 100-row stratified sample (25 per class) labeled by hand gives the precision/recall numbers needed to decide whether `data/misinfo_carriers.csv` and `docs/FINDINGS.md` are publishable.

## Setup

```bash
# Build the template (default 25 per class, seed 42)
python pipeline/gold_set_build.py
ls -la data/gold_set_template.csv
```

Open in Excel, Google Sheets, or LibreOffice Calc. The CSV has 15 columns; resize and wrap text — `evidence_quote` and `llm_reasoning` can be long.

## (Recommended) Sort by `llm_verdict`

Sort rows so all 25 of one class are together. Calibration is faster when you do one class at a time. The `pair_id` column preserves identity, so sorting doesn't break anything.

## The four labels

You're judging *what the article actually does with the claim*, not whether the claim is true or false.

| Label | Meaning |
|---|---|
| `carrying` | Article presents the claim as fact, without refutation. Reader walks away believing it. |
| `debunking` | Article actively refutes or fact-checks the claim. |
| `neutral_reporting` | Article mentions the claim explanatorily ("X says Y; experts disagree") — neither endorsing nor refuting. |
| `irrelevant` | Article doesn't address this claim at all. The Stage 4a embedding match was a false signal. |
| `skip` | Genuinely ambiguous, or the article body is unreadable. Excluded from metrics — better than guessing. |

## Decision flow per row

For most rows you can decide from the CSV alone. Read in this order:

1. `claim_text` — what's the claim?
2. `evidence_quote` — what passage from the article did the LLM pick?
3. `llm_reasoning` — what's the LLM's logic?

If those three tell a coherent story, you have your label.

**For every `carrying` row, click `article_url` and verify in the article body**:

- Is the `evidence_quote` actually present, or did the LLM hallucinate it?
- Is the surrounding context what the LLM described (uncritical presentation), or did the LLM miss a refutation a few paragraphs later?
- Is the `claim_text` actually what the article is saying, or is it a different but similar-sounding claim?

If any of these fail → label as whatever the article *actually* does (`debunking` / `neutral_reporting` / `irrelevant`).

This is the labor-heavy step but it's the precision number that determines whether the carrier list is publishable.

## What not to touch

Only `human_verdict` and (optionally) `notes` should change. Everything else (`pair_id`, `llm_verdict`, `similarity`, `article_*`, `claim_*`, `fact_check_*`, `evidence_quote`, `llm_reasoning`) is reference data.

## Save and run

```bash
# Save as data/gold_set_labeled.csv (the path the eval reads by default).
# Excel: "Save As → CSV UTF-8". Sheets: "Download → CSV".
ls -la data/gold_set_labeled.csv

python pipeline/gold_set_eval.py
```

Output:

- **Confusion matrix** — rows = your labels, columns = LLM verdicts. Diagonal = correct.
- **Per-class precision/recall/F1** — `precision` = of LLM-flagged X, what % were really X. `recall` = of actually-X, what % the LLM caught.
- **Carrier false-positives** — LLM said `carrying`, you said something else. Most damaging error class.
- **Carrier false-negatives** — you said `carrying`, LLM disagreed. Less damaging but informative.

Persisted to `data/gold_set_metrics.json` for cross-run diffs.

## Interpreting the result

| Carrier precision | What it means |
|---|---|
| ≥ 0.85 | Safe to publish FINDINGS with light human review |
| 0.70 – 0.85 | Publishable with mandatory per-row review |
| < 0.70 | Don't publish until the failure mode is identified and fixed |

If the number is ugly, surfacing it is the point. The alternative is shipping a number you can't defend.

## Time budget

- ~30–60 min for a careful 100-row pass.
- The `irrelevant` and `debunking` rows are usually quick (decide from `evidence_quote` + `llm_reasoning` alone).
- The `carrying` rows take most of the time because each needs an article click-through.

## Faster alternative: Claude-as-judge

If 30–60 min isn't realistic, send each row's article + claim + class definitions to Claude (Sonnet 4.6 or Opus 4.7) and let it fill `human_verdict`. Spot-check ~10 rows by hand, then run `gold_set_eval.py`.

Trade-offs:
- **Faster**: ~5 min vs ~60 min, ~$0.50-2.00 API spend.
- **Less trustworthy**: 90-95% agreement with a careful human reviewer; "Claude judging qwen3" introduces some correlated error (both are LLMs, both can be fooled by similar framings).
- **Better than nothing**: which is the current state.

A small `gold_set_label_with_claude.py` script for this can be added on request.
