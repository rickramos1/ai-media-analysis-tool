# Local LLM Accuracy Challenges — Research Brief

## Purpose

This document captures everything we've learned about local LLM (currently `qwen3:14b` via Ollama on bigdoggie) accuracy in the cross-reference misinformation pipeline. It exists to seed a research project: **find a better local model, prompt strategy, or pipeline architecture for this task without giving up the local-LLM commitment**.

Cloud LLMs (Claude Opus 4.7) may be used **only for evaluation and validation** — measuring local-LLM accuracy. The production pipeline must remain local-LLM-driven.

## Architectural commitment

- **Production inference must run on local GPU (bigdoggie, RTX 4080, 16 GB VRAM).**
- Cloud LLMs are validation tools only — they label gold sets, judge precision/recall, and benchmark candidate local models. They never enter the runtime path.
- Model choice is open within the local-LLM constraint. The current production model is `qwen3:14b` (Q4_K_M, ~12 GB weights). Any candidate replacement must fit the VRAM budget with usable `num_ctx` and acceptable per-call latency.

## Measured accuracy ceiling

The only stage with a measured ground-truth comparison is **Stage 4b (carrier verification)**. A 100-row stratified gold set (25 per class: `carrying`, `debunking`, `neutral_reporting`, `irrelevant`) was labeled by Claude Opus 4.7 acting as judge. Eval against qwen3:14b's verdicts:

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| carrying | **0.840** | **1.000** | 0.913 | 21 |
| debunking | 1.000 | 0.926 | 0.962 | 27 |
| neutral_reporting | 0.760 | 0.950 | 0.844 | 20 |
| irrelevant | 1.000 | 0.781 | 0.877 | 32 |

**Overall accuracy: 90.0%.**

The per-class confusion is asymmetric: qwen3 over-flags `carrying` (4 false-positives in 25 sampled; ~16% FP rate) and under-flags `irrelevant` (often calling it `neutral_reporting`). It never misses a real `carrying` verdict in the sample (recall 1.00).

### Carrier false-positive pattern

3 of the 4 `carrying` false-positives share one structural pattern: **quote-then-refute**.

The article quotes the misinfo claim from someone, then refutes or contextualizes it elsewhere in the body. qwen3 sees the quote, classifies "carrying," and misses the refutation. Examples from the gold set (preserved in `data/gold_set_labeled.csv`):

- **foxnews.com** — Schumer's claim quoted as Dem talking point, then countered by Dannenfelser/Lankford/Francis quotes pushing back. qwen3 labeled `carrying`; cloud judge labeled `neutral_reporting`.
- **cbsnews.com** — Kennedy/Makary cite EPPC's mifepristone-harm claim, then *immediately* rebutted by CBS medical contributor Dr. Gounder ("Other data sources show... less than 1 in 200") and ACLU. qwen3 labeled `carrying`; cloud judge labeled `debunking`.
- **dailysignal.com** — Op-ed quotes a clinic worker calling abortion pills "safe and easy" then the author refutes that framing based on personal harm. Setup-then-attack structure. qwen3 labeled `carrying`; cloud judge labeled `debunking`.

The 4th false-positive is a different pattern: **embedding-retrieval false signal**. Stage 4a's nomic-embed-text matched a topical-but-irrelevant article-claim pair; qwen3 then forced it into one of the four classes instead of returning `irrelevant`.

### Failed mitigation attempts (two distinct strategies)

**Attempt 1: Stronger main prompt.** Revised the Stage 4b classification prompt to instruct qwen3 to "scan the entire article for any refutation before classifying as carrying."

- Carrier precision dropped 0.84 → **0.50**
- Carrier recall dropped 1.00 → **0.36** (lost ~64% of real carriers)
- Overall accuracy dropped 90.0% → **29.0%**

qwen3 over-corrected: interpreted *any* contrasting framing — including the standard journalistic "critics say" gesture — as refutation. Reverted.

**Attempt 2: Post-processing refutation-check (focused yes/no second pass).** Kept the original Stage 4b prompt. For each `carrying` verdict, ran a second isolated prompt asking just: "Does the article contain DIRECT refutation? Quote it, or NO." Implementation in `pipeline/stage4b_refute_check.py`.

- 27 demotions out of 315 carrying verdicts
- Hand-audit of all 27 found **~57% were wrong demotions** — qwen3 routinely treated *supportive citations* of the claim as "refutations"
- Most damning case: the model's own `reasoning` field said the article "directly supports the previously debunked claim" but it still demoted the verdict to debunking
- Reverted from backup

**Diagnosis (consistent across both attempts)**: qwen3:14b cannot reliably distinguish "this paragraph supports the claim" from "this paragraph refutes the claim" when both appear in the same article body. Two distinct prompting strategies — full classification rewrite, isolated yes/no second pass — hit the same wall in the same place.

**This is the central accuracy challenge for the pipeline**: prompt engineering does not move the underlying frontier on this discrimination task. Different prompts trade FP rate against FN rate but the model lacks the cross-paragraph stance-detection precision required. The next move has to be a **better model**, not a better prompt.

## Pipeline stages and accuracy status

| Stage | Model | Measured? | Numbers |
|---|---|---|---|
| Stage 1 — article classification | qwen3:14b | **No** | Smoke test: 3/3 hand-crafted cases correct; no real eval |
| Stage 2 — claim extraction | qwen3:14b | **No** | BACKLOG calls for a 6-article test set; never built |
| Stage 3 — ideology cross-reference | (no LLM, rule-based) | yes | Deterministic; correctness depends on `IDEOLOGY_MAP` coverage |
| Stage 3.5 — claim normalization | qwen3:14b | partial | 4/5 batches parse cleanly at chunk_size=40; 1 batch needed singleton fallback |
| Stage 4a — embedding retrieval | nomic-embed-text | partial | 1/1682 chunks failed (HTTP 400, length-limit edge case); pipeline handled with zero-vector fallback |
| Stage 4b — carrier verification | qwen3:14b | **Yes** | precision 0.84 / recall 1.00 / accuracy 90% on 100-row gold set |
| Stage 5 — report generation | (no LLM) | yes | Deterministic |

**The accuracy of the pipeline as a whole is unknown** because Stages 1, 2, and 3.5 are unmeasured. Stage 4b's 0.84 precision is the only honest precision number; an end-to-end accuracy estimate requires gold-set evals at each LLM-using stage.

## Failure mode taxonomy

Categorized for research-project use — each is a candidate target for "does a different model fix this?" experiments.

### 1. Quote-then-refute confusion (Stage 4b)
The dominant carrier-FP pattern. Article quotes the misinfo claim, then rebuts or contextualizes it elsewhere. qwen3 cannot reliably distinguish substantive refutation from token "critics say" framing.

**Hypothesized cause**: 8K context + 14B parameters insufficient for cross-paragraph reasoning over article-length text. Model can't track which speaker said what.

**Candidate fixes**: larger model with more context (qwen3:32b at higher num_ctx if VRAM allows), reasoning models (DeepSeek-R1, gpt-oss-style models), structured two-pass approach (carrying-then-refutation-check with separate prompts).

### 2. `<think>` budget burn (all qwen3 stages — fixed)
**Status: mitigated.** qwen3 silently ignores the `/no_think` prompt directive and emits `<think>...</think>` tokens that consume the entire `num_predict` budget, leaving `response: ""` with `done_reason: "length"`. Documented as a Stage 4b "UNKNOWN parse-fail" issue at ~20% rate, mitigated historically by bumping `num_predict` to 1500.

**Real fix applied**: pass `"think": false` at the top level of the Ollama `/api/generate` payload (NOT inside `options`). Confirmed working on Ollama 0.17.1. Eliminates the failure mode entirely.

**Throughput impact**: Stage 1 went from ~9 s/row → ~0.7 s/row (10×). Stage 4b went from 0.15-0.2 pairs/s → ~0.9 pairs/s (~5×). This was the single biggest engineering win in the project.

**Research implication**: any candidate replacement model needs a similar reasoning-suppression mechanism, or the prompts need to be explicitly chain-of-thought-friendly. Reasoning models (DeepSeek-R1) may have the same budget issue; pure non-reasoning models (Llama 3.3, Mistral, Gemma) avoid it.

### 3. Single-call structured-output fragility (Stage 3.5 — fixed)
At ≥150 input claims with `num_ctx=8192`, qwen3 returned prose markdown summaries instead of the requested JSON cluster object. Mitigated by chunking input into batches of ~40 claims with cross-batch fuzzy merge of canonical-claim text. Even at chunk_size=40 with `think:false`, ~1 in 5 batches still failed to parse and fell back to singleton families.

**Final fix shipped**: Ollama's `format=` JSON Schema parameter passed to both Stage 3.5 (`pipeline/claim_normalizer.py`) and Stage 4b (`pipeline/stage4b_verify.py`). Token-level grammar-constrained generation guarantees the response parses as valid JSON matching the schema. The chunk_size=40 + singleton-fallback machinery is preserved as defense in depth but is no longer load-bearing for the parse-success rate.

**Stage 4b enum constraint**: the `verdict` field is now `enum: ["carrying", "debunking", "neutral_reporting", "irrelevant"]`. Invalid verdict strings are structurally impossible; the historical Stage 4b "UNKNOWN" parse-fail rate goes to zero.

### 4. Hallucinated evidence quotes (Stage 4b — quantified, fixed retroactively)
The Stage 4b verifier emits an `evidence_quote` field — a passage from the article supporting the verdict. The original prompt permitted "tight paraphrase" alongside literal quotes; qwen3 interpreted this liberally.

**Quantified**: substring-match audit on the 315 carrying verdicts found **91 (29%) hallucinated quotes** — 66 pure paraphrases (no transparency about reconstruction), 25 stitched abridgments (with `...` or `[...]` markers).

**Fix shipped (two layers)**:
1. **Prevention going forward**: `pipeline/stage4b_verify.py` now runs `quote_in_article()` after every call (whitespace + smart-quote normalized substring check, ≥12 char threshold). If the quote isn't in the article body, it's set to null and `evidence_quote_hallucinated: true` is added to the verdict for auditability. Future runs cannot publish hallucinated quotes.
2. **Retroactive cleanup**: `pipeline/stage4b_quote_reextract.py` re-extracted the 91 affected quotes with a strict-literal prompt + `format=` schema + the validator + 1 retry. Result: 79 (87%) recovered as verifiable literal quotes; 12 (13%) honestly nulled. Post-cleanup hallucination rate: 0%.

**Surprise finding**: the hallucinations were almost entirely a *prompt-permission issue*, not a capability gap. Smoke test of the strict-literal prompt: 5/5 produced clean literal quotes on the first attempt. qwen3 *can* extract literal quotes when the prompt and validator structurally enforce it. The original prompt's "tight paraphrase" allowance was load-bearing; removing it fixed the failure mode.

**Open follow-up**: bake the strict-literal prompt into the main `verify()` so quotes are correct at generation time, not validated post-hoc. Smoke test suggests this works without regression risk.

### 5. Embedding chunk-length failures (Stage 4a — handled)
nomic-embed-text rejects chunks longer than 2048 tokens with HTTP 400. Empty strings same issue. Stage 4a now truncates to 1500 words and falls back to single-item embed calls on batch failure (filling failed items with zero vectors).

**Status**: handled but not fully solved. Failed items become zero vectors that never match anything — silent recall loss. On the current corpus, 1/1682 chunks (0.06%) hit this; not material at current scale, but a candidate concern for larger corpora.

**Candidate fixes**: smarter chunking (sentence-boundary-aware), different embedding model with longer context (e.g. nomic-embed-text-v2 at 8192, bge-large at 512 with proper chunking, e5-mistral at 4096).

### 6. Embedding retrieval false matches (Stage 4a)
nomic-embed-text matches articles to claims based on topic-level cosine similarity. This generates candidates that are *topically* similar but don't actually engage the claim — Stage 4b is supposed to filter these out as `irrelevant`. The 4th carrier-FP from the gold set was exactly this: topical match, qwen3 forced it into `carrying` instead of `irrelevant`.

**Hypothesized cause**: nomic-embed-text optimizes for general semantic similarity, not for "this article makes this specific claim."

**Candidate fixes**: claim-specific embedding models, hybrid retrieval (BM25 + dense), or query rewriting (expand the claim into multiple paraphrases for retrieval).

## Engineering mitigations already applied

For continuity — anyone working the research project should know what's already been tried:

- **`"think": false`** API toggle across all qwen3 stages (`article_classifier.py`, `claim_extractor.py`, `claim_normalizer.py`, `stage4b_verify.py`, `misinfo_detector.py`) — eliminated `<think>` budget burn (10× speedup on Stage 1, ~5× on Stage 4b)
- **Ollama `format=` JSON Schema** on Stage 3.5 + Stage 4b — token-level grammar-constrained generation; eliminates JSON-shape failures and Stage 4b enum-violation parse-fails
- **`evidence_quote` substring validator** in `stage4b_verify.py` — auto-nulls hallucinated quotes, flags with `evidence_quote_hallucinated: true` for audit
- **Quote re-extraction** (`stage4b_quote_reextract.py`) — strict-literal prompt + validator + retry; drove carrier-pool hallucination rate from 29% to 0% retroactively
- **External fact-check seed** (`external_factchecks.py`) — Google Fact Check Tools API integration enlarged the canonical claim universe
- **Chunked clustering** in Stage 3.5 with rapidfuzz cross-batch merge
- **Resume/checkpoint** in long-running stages (Stage 4b)
- **Multi-ideology + authoritative-solo cross-reference** in Stage 3 to filter weak debunks
- **Source-name fuzzy normalization** (rapidfuzz `token_set_ratio ≥ 85`)
- **Hybrid topic gate**: regex topic-context OR semantic similarity ≥ 0.70
- **Syndicate dedupe** via union-find on cosine ≥ 0.95
- **Fallback paths** (e.g., Stage 4a reads `claims_verified.json` if `claim_families_filtered.json` missing)
- **`num_predict=1500`** historically on Stage 2 / Stage 4b to compensate for `<think>` budget burn — now redundant since `think: false`, could be dropped

## Architectural constraints

### VRAM math (RTX 4080, 16 GB)

`qwen3:14b` Q4_K_M weights = ~12 GB. Remaining 4 GB is shared between KV cache slots (`OLLAMA_NUM_PARALLEL` × per-slot KV at chosen `num_ctx`) and other system overhead.

| `NUM_PARALLEL` | Per-slot KV at 16 k ctx | Total | Fits? |
|---|---|---|---|
| 2 | 1.4 GB × 2 = 2.8 GB | 14.8 GB | ✓ |
| 4 | 1.4 GB × 4 = 5.6 GB | 17.6 GB | ✗ (CPU spill) |
| 4 + `num_ctx=8192` | 0.7 GB × 4 = 2.8 GB | 14.8 GB | ✓ |

Pipeline scripts default to `num_ctx=8192` for this reason. Bumping to 16k spills to CPU and runs ~6× slower.

**Implication for candidate models**: anything ≥ 14B at Q4 needs context ≤ 8K to coexist with 4-way parallelism. Bigger models (32B, 72B) need either GPU upgrades or aggressive quantization (Q3, Q2) at potentially significant accuracy cost.

### GPU stranding
If another process holds the GPU when qwen3 first loads, Ollama silently falls back to CPU and stays there until manually unloaded. Symptom: `/api/ps` shows `size_vram: 0`. Recovery: `POST /api/generate {"model":"qwen3:14b","keep_alive":0}` then re-prompt to force GPU reload.

**Implication for research**: any benchmark of candidate models needs a check that the model actually loaded on GPU before timing.

## Conventions and foot-guns discovered

For anyone running benchmarks against new models — the things we got wrong before getting right:

- **`/no_think` in prompt**: silently ignored by qwen3. Don't trust it.
- **`think: false` placement**: top-level in `/api/generate` payload. NOT inside `options`. Wrong location = silently ignored.
- **`num_predict` bumps to compensate for thinking**: legacy mitigation, no longer load-bearing post-`think:false`. Could be reduced to ~400.
- **Ollama `num_ctx` default vs requested**: Ollama may use a different ctx than you ask for if VRAM is tight. Check `/api/ps` after first load.
- **Ollama timeout vs request timeout**: client-side `timeout=300` doesn't mean Ollama gave up; it means *we* gave up waiting. The model may still finish.
- **`OLLAMA_LLM_LIBRARY=cuda_v12`** keeps reverting on bigdoggie (Ollama tray app re-asserts on login). Doesn't usually matter but can cause silent perf regressions.
- **`OLLAMA_NUM_PARALLEL=4`** is the bigdoggie default; assumption baked into pipeline scripts. Different value changes the VRAM math.

## Candidate research directions

In rough order of expected impact-to-effort ratio:

### A. Larger qwen3 (32B, 72B)
**Why try**: same model family, likely better at the cross-paragraph reasoning that the quote-then-refute pattern needs.
**Constraint**: 32B at Q4 = ~20 GB → spills VRAM on the 4080. Either Q3/Q2 quantization (accuracy hit unknown) or GPU upgrade.
**How to evaluate**: re-run gold_set_eval against new model.

### B. Reasoning models (DeepSeek-R1, gpt-oss style)
**Why try**: explicitly trained for the kind of multi-step "scan article, locate claim, scan for refutation, classify" reasoning that the task needs.
**Risk**: same `<think>`-budget issue as qwen3 if not properly suppressed. May need different prompting conventions.
**How to evaluate**: same gold set, but plan for longer per-call latency.

### C. Different model families at similar size
- Llama 3.3:70b (instruct-tuned, known strong on classification)
- Mistral Small 3 / Large
- Gemma 3:27b (Google, recently released, strong on instruction-following)
- Phi-4:14b (Microsoft, optimized for reasoning at small scale)

**Why try**: rule out qwen3-specific weaknesses. If Phi-4:14b gets to 0.92 on the same gold set, the issue was qwen3 not size.
**How to evaluate**: same gold set, controlled prompt.

### D. Fine-tuned model
**Why try**: directly optimize for our task. Train on a labeled dataset of `(article, claim) → verdict` pairs.
**Effort**: high. Need 500+ labeled pairs (have 100), QLoRA fine-tuning infrastructure, eval harness.
**Payoff**: potentially the largest accuracy gain if the gold set can be expanded.

### E. Two-pass verification (post-processing rule) — **ATTEMPTED AND FAILED**
**Plan**: keep the original Stage 4b prompt. For each `carrying` verdict, run a second focused yes/no prompt on qwen3: "Does this article contain any text that DIRECTLY refutes the claim — counter-quote from a doctor/regulator/scientist, contradicting statistics, author dispute? Answer 'YES' with quote, or 'NO'." If YES → demote to `debunking`. Implementation in `pipeline/stage4b_refute_check.py`.
**Result on full 315-carrying pool**: 27 demotions. Hand-audit of all 27 found ~57% wrong demotions — qwen3 routinely flagged *supportive citations* of the claim as "refutations." The most damning case: the model's own `reasoning` field said "directly supports the previously debunked claim" but it still demoted to debunking. Reverted from backup.
**Diagnosis**: same blindspot as the failed prompt revision (failure mode #1). qwen3:14b cannot reliably distinguish "this paragraph supports the claim" from "this paragraph refutes the claim" when both appear in the same article body. The focused yes/no framing didn't fix the underlying discrimination problem. The script (`pipeline/stage4b_refute_check.py`) is preserved for re-testing against future candidate models.
**Implication**: this is the strongest piece of evidence for the research project's central question. Two distinct prompting strategies (full classification rewrite, isolated yes/no second pass) hit the same wall in the same place. The fix has to be a **better model**, not a better prompt.

### F. Ensemble methods
**Why try**: combine verdicts from multiple local models, take majority vote or require all-agreement for `carrying`.
**Effort**: 2-3× the inference cost. Marginal gain expected unless the models have uncorrelated failure modes.

### G. Better embedding model (Stage 4a)
**Why try**: reduces the "irrelevant misclassified as carrying" failure mode by giving Stage 4b cleaner candidates.
**Candidates**: bge-large-en-v1.5, e5-mistral-7b, jina-embeddings-v3, nomic-embed-text-v2.
**How to evaluate**: measure precision@K on a gold set of (article, claim, is_relevant) tuples. Doesn't yet exist; would need building.

## Evaluation harness already in place

For the research project — these are the existing tools:

- **`pipeline/gold_set_build.py`** — stratified sampler (default 25 per verdict class, 100 total). Can rebuild from any `stage4b_verdicts.json`.
- **`pipeline/gold_set_eval.py`** — confusion matrix + per-class precision/recall/F1 + carrier FP/FN listing. Supports renamed columns via `--judge-col` / `--llm-col` flags.
- **`pipeline/gold_set_reverify.py`** — runs Stage 4b's `verify()` against gold-set pair_ids only; writes new column for diff comparison. Useful for testing prompt or model changes without re-running the full Stage 4b. Known limitation: pair_ids built pre-audit may not match current verdicts file; affected rows reported as misses.
- **`pipeline/stage4b_refute_check.py`** — focused yes/no second-pass over `carrying` verdicts (post-processing demotion based on detected refutation). Empirically failed on qwen3:14b (~57% wrong demotions on hand-audit); preserved as a candidate-model regression test.
- **`pipeline/stage4b_quote_reextract.py`** — re-extracts hallucinated `evidence_quote` values with a strict-literal prompt + `format=` schema + substring validator + 1 retry. Drove the carrier-pool hallucination rate from 29% to 0%.
- **`data/gold_set_labeled.csv`** — 100 rows labeled by Claude Opus 4.7 acting as judge. Treat as ground truth for now; expand and human-verify a subset for higher confidence.
- **`data/gold_set_metrics.json`** — most recent eval output for cross-run diffs.

### Suggested research-project workflow

For each candidate model:

1. Load model in Ollama: `ollama pull <model>`
2. Verify on GPU: `curl /api/ps | jq '.models[].size_vram'`
3. Set `OLLAMA_MODEL=<candidate>` in env or override per-run
4. Run targeted reverify: `python pipeline/gold_set_reverify.py` (writes `gold_set_labeled_v2.csv`)
5. Compare: `python pipeline/gold_set_eval.py --input data/gold_set_labeled_v2.csv --judge-col cloud_llm_verdict --llm-col ollama_verdict_v2`
6. Record: precision, recall, accuracy, per-class F1, and any new failure-mode patterns

A controlled benchmark of 5-7 candidate models against the same gold set should be ~2 hours of work plus inference time, and would meaningfully narrow the search.

### Gold-set expansion

The current 100-row gold set is too small for confident model selection — a precision number of 0.84 on 25 carrying samples has a 95% CI of roughly ±15%. To reliably distinguish a 0.84 model from a 0.92 model, the gold set needs ~300-500 carrying examples.

**Path**: rebuild from the full `stage4b_verdicts.json`, sample 100 per class (400 total), label with Claude (cost ~$2-8) and human-spot-check 10% for cloud-judge correctness.

## Caveats

- The 0.84 precision number rests on Claude-as-judge labels, not human labels. Cloud-judge agreement with a careful human reviewer is typically 90-95%; this introduces ~5-10% measurement noise. For research purposes that's acceptable; for the *publication-grade* precision number, a 30-50 row human-verified subset is recommended.
- All measurements are on the current corpus (1,159 eligible articles, 91 canonical claim families). Generalization to other women's-health corpora or to other domains is untested.
- The pipeline has been tuned against this corpus through ~5 iterations of audit and refinement. Some of the apparent quality may reflect overfitting to the corpus rather than model capability.

## Open questions

- Does qwen3:32b (Q4 quantized, would barely fit in 16 GB at low parallelism) get to 0.90+ carrier precision?
- Can Phi-4:14b (similar size, different lineage) match or exceed qwen3:14b on this task?
- Is the `<think>` reasoning trace, when *kept* (not suppressed), more accurate than fast-answer mode? Worth testing reasoning models in their native mode.
- How much of the 0.84 ceiling is model capability vs prompt design? A controlled "same model, three prompts" experiment would isolate this.
- Does fine-tuning on 500 labeled pairs move precision more than swapping to a 5× larger off-the-shelf model? Expensive to find out, but it's the question that decides whether the project should invest in fine-tuning infrastructure.
