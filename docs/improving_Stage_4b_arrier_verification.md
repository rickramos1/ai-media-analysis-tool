# Improving Stage 4b Carrier Verification: A Research Report

**Date: April 27, 2026**
**Scope: Local-LLM accuracy improvements for a 4-class misinformation classifier on RTX 4080 (16 GB)**

---

## Executive Summary

Stage 4b's failure mode is well-characterised in the literature: it is the classic "quote-then-refute" stance-detection problem, and a single-pass prompt that asks a 14B model to reason globally about an article's stance is the wrong tool for it. Three changes will move the needle more than swapping models alone:

1. **Decompose Stage 4b into two passes.** First pass: extract claim-relevant sentences with speaker attribution. Second pass: classify the article's stance toward the claim conditioned on those structured spans. This pattern (a generate-expand-verify or "verify-then-classify" cascade) is the most consistent winner in 2024–2026 fact-checking literature (FEVER 2024 HerO, Multi-stage Pipelines, Toward Reliable Clinical Coding).
2. **Switch the backbone for a benchmark sweep, but keep Qwen3 14B as the baseline.** The most credible challengers given the 16 GB hard constraint are **Qwen3 14B-Instruct-2507**, **Phi-4-reasoning 14B**, **Gemma 3 12B**, **Mistral Small 3.2 24B (Q4_K_M)**, **gpt-oss-20b (MXFP4 native)**, and **gpt-oss-safeguard-20b**. The last is purpose-built for "classify content against a written policy" and is the single most aligned new model with the user's task.
3. **Fine-tune.** A QLoRA adapter on Qwen3 14B (or Phi-4 14B) trained on ~500 hand-curated + ~1,500 synthetic adversarial quote-then-refute examples is the highest-expected-value intervention for this specific failure mode. Published case studies show 7B-14B fine-tunes typically deliver +10–20 F1 over zero-shot on stance/classification tasks, and the sweet spot is 200–500 well-curated examples with diminishing returns past ~5K. Unsloth on the user's RTX 4080 will fit 14B QLoRA at sequence length 2048, with merged GGUF Q4_K_M export to Ollama in a single notebook.

The prompt-only "scan for refutation" instruction regressed because it added an unconditional bias — instructing a model to look for refutation makes it find refutation everywhere. Decomposition (Section C) and fine-tuning (Section D) replace that brittle instruction with structured evidence extraction the model can reason over.

---

## Section A: Local-Model Shortlist for Benchmarking on the Gold Set

### Constraints recap

The user's 16 GB / `OLLAMA_NUM_PARALLEL=4` / `num_ctx≥8192` budget is a hard envelope. Independent measurements on the RTX 4080 confirm that Qwen3 14B Q4_K_M lands at ~12 GB resident with a 19K context (Glukhov, March 2026 benchmark using Ollama 0.17.7), and the GPU saturates at roughly 51–62 tokens/sec on 14B-class Q4 models. Any 27B+ dense model at Q4 needs ~17–19 GB and will spill to CPU at parallel=4. Two practical implications:

- **The realistic ceiling is ~14B dense at Q4 or ~20B sparse at MXFP4** if the user wants to keep parallel=4. Lowering to parallel=2 unlocks Mistral Small 3.2 (24B Q4_K_M ≈ 14 GB) cleanly and 27B Q4 marginally.
- **Aggressive quantisation (Q2/Q3) on 32B models is not recommended.** The empirical Qwen3 quantisation study (arXiv 2505.02214) shows competitive scores at 8-bit and reasonable 4-bit, but ultra-low precision (2–3 bit) causes "notable degradation in linguistic tasks," with perplexity rising by orders of magnitude in some configs. Long-context tasks suffer disproportionately under 4-bit (Long-context quantization study, arXiv 2505.20276, finds drops up to 59% on 4-bit BNB-nf4 in some Llama models). For a stance task that depends on tracking who-said-what across paragraphs, Q3/Q2 32B is a worse bet than Q4 14B.

### Ranked shortlist (highest expected value first)

| Rank | Model | Ollama tag | Q4_K_M VRAM | Max ctx @ parallel=4 in 16 GB | Reasoning toggle | Why it's on the list |
|---|---|---|---|---|---|---|
| 1 | **Qwen3-14B (latest)** | `qwen3:14b` | ~9 GB weights, ~12 GB total | 8K easy, 16K tight | Yes (`/think`, `/no_think`, `enable_thinking=False`) | Current production baseline. Strong general instruction-following, hybrid reasoning, mature Ollama support. The control. |
| 2 | **gpt-oss-safeguard-20b** | `gpt-oss-safeguard:20b` | ~13 GB (MXFP4 native, MoE 21B/3.6B-active) | 8K with parallel=4; 32K at parallel=2 | Yes (`reasoning_effort: low/medium/high`) | Purpose-built for "classify content against a developer-supplied written policy." Trained to reason from a policy → label, with a Harmony-format dedicated reasoning channel. Apache 2.0. *This is the single best architectural fit for the carrier/debunking/neutral/irrelevant taxonomy.* |
| 3 | **Phi-4-reasoning 14B** | `phi4-reasoning:14b` (or `phi4-reasoning:plus`) | ~9 GB at Q4_K_M | 8K easy, 32K native ctx | Always-on reasoning trace (this is its mode) | Microsoft's 14B reasoning model. Outperforms DeepSeek-R1-Distill-70B on reasoning benchmarks and shows strong cross-domain generalisation. The most credible Qwen3 challenger at the same parameter count. |
| 4 | **gpt-oss-20b** | `gpt-oss:20b` | ~13 GB MXFP4 native | Comparable to safeguard | Yes (low/medium/high) | Same architecture as safeguard but general-purpose. Useful as the baseline for the safeguard variant and as an independent-error-mode ensemble member. Native function calling and structured outputs. |
| 5 | **Gemma 3 12B (QAT)** | `gemma3:12b-it-qat` | ~7–8 GB | 16K comfortable, 32K achievable | No native reasoning toggle | Google's instruction-tuned 12B with 128K native context and a KV-cache-efficient architecture (high local-to-global attention ratio explicitly designed to keep KV small). Strong instruction-following reputation, QAT variants preserve quality at 4-bit. The best "fits with headroom" option. |
| 6 | **Mistral-Small-3.2 24B** | `mistral-small3.2:24b` | ~14 GB at Q4_K_M | 8K at parallel=2 (tight at parallel=4) | No | Mistral's January→June 2025 lineage, with 3.2 specifically improved on instruction following, repetition errors, and function calling. Strong JSON output. Trade off: requires dropping to parallel=2 to fit comfortably. |
| 7 | **DeepSeek-R1-Distill-Qwen-14B** | `deepseek-r1:14b-qwen-distill-q4_K_M` | ~9 GB | 8K easy | Always-on reasoning | Distilled from full DeepSeek-R1 onto Qwen 2.5 14B base. Strong reasoning lift on structured tasks, and useful as a third independent error-mode model. The R1-0528 update (May 2025) significantly improved its reasoning. |

### Models considered and rejected (with rationale)

- **Qwen3 32B at Q3/Q2** — research literature (Qwen3 quantisation study, May 2025; long-context quantisation study, May 2025) shows that 2–3 bit hurts long-context linguistic tasks disproportionately. The user's task is exactly that — tracking attribution across paragraphs. **Recommendation: do not pursue.** A Q4 14B fine-tune is a better use of the budget.
- **Qwen3 30B-A3B Instruct-2507 / Qwen3.5-35B-A3B / Qwen3.6-35B-A3B (MoE)** — at Q4_K_M these need ~17–18 GB resident and spill on a 16 GB card. They are excellent models but do not satisfy the hard constraint with parallel=4. If the user is willing to drop to parallel=1, the Qwen3-30B-A3B-Instruct-2507 Q4 is one of the best non-thinking instruction models available and is worth a side experiment.
- **Gemma 3 27B** — same VRAM problem; 17 GB Q4 spills.
- **Llama 3.3 70B / Llama 4** — far outside 16 GB; not viable locally.
- **Command-R7B** — small (7B), grounded-generation/citation-aware, but the user already gets stronger reasoning from Qwen3 14B. Worth knowing about for the Stage 4b `evidence_quote` field (its native grounding tags emit citation spans) but not the right primary classifier. There is no first-party Ollama Command-R7B tag — community ports exist.
- **Qwen3-VL** — vision-language; the pipeline is text-only, so vision capability is wasted weight.
- **Qwen3-Coder** — coding-specialised; worse on natural-language stance than the base instruct.
- **Qwen3.5 9B / 27B / 35B-A3B** (released February 2026) — the 9B fits easily and is a genuine candidate to add as #8 on the list (~6 GB Q4, ~90 tok/s on RTX 4080 per Glukhov benchmark). The 27B is borderline (Q4 ≈ 17 GB) and the 35B-A3B MoE is over budget at parallel=4. Add `qwen3.5:9b-q4_K_M` to the sweep if available in your Ollama version — it pairs nicely with a 14B model in an ensemble.
- **Granite 3.3 8B Instruct** — IBM, structured reasoning with `<think>` tags, decent on RAGBench. Good but 8B is below Qwen3 14B's ceiling on the same task.

### Installation commands (sweep)

```bash
ollama pull qwen3:14b
ollama pull qwen3:14b-instruct-2507-q4_K_M    # if your Ollama version exposes 2507
ollama pull gpt-oss-safeguard:20b
ollama pull gpt-oss:20b
ollama pull phi4-reasoning:14b
ollama pull gemma3:12b-it-qat
ollama pull mistral-small3.2:24b
ollama pull deepseek-r1:14b-qwen-distill-q4_K_M
# optional ensemble member
ollama pull qwen3.5:9b
```

For each, run `gold_set_eval.py` with `num_ctx=8192`, `num_parallel=4`, `temperature=0`. For reasoning models, run twice: once with thinking on, once with thinking off (or `reasoning_effort: low` for gpt-oss).

### Specific reasoning on the user's open questions

- **"Does Qwen3:32B at Q3/Q2 preserve enough quality?"** Empirically, no — the Qwen3 quantisation study and the long-context quantisation study both show ultra-low-bit hurts linguistic and long-context tasks disproportionately. A Q4 14B fine-tune will beat a Q2 32B zero-shot on this kind of pragmatic-stance task. Not recommended.
- **"Can Phi-4 14B match or exceed Qwen3 14B on classification?"** Plausibly yes on reasoning-heavy decisions, plausibly no on instruction-following polish. Phi-4-reasoning beats DeepSeek-R1-Distill-Llama-70B on reasoning benchmarks and Phi-4 base has competitive MMLU (84.8) versus Qwen2.5-14B (~79). On classification specifically, published comparisons (LLM-Stats, awesomeagents.ai February 2026) show Phi-4 winning on STEM/reasoning and Qwen3-14B winning on instruction following and general agent tasks. **Test it; don't pre-decide.** Phi-4 has a natural advantage on the quote-then-refute problem because of the reasoning trace.
- **"Is reasoning mode actually more accurate on classification despite the 5–10x latency?"** The published evidence is split. The "Explicit Reasoning Makes Better Judges" paper (arXiv 2509.13332) finds Qwen3-4B in thinking mode gets +10.5 points over non-thinking on judge-style evaluation with only 1.82× FLOPs — i.e., reasoning is more cost-efficient than 7-shot ICL. But the same paper warns smaller models can't always exploit reasoning, and the medical reasoning thinking-budget study (arXiv 2508.12140) finds that for routine clinical-support tasks, the 256–512 reasoning-token regime is optimal — beyond that, returns diminish sharply. For a 4-way classification with structured input, expect modest gains (a few F1 points) and large latency cost. **Worth testing on Phi-4-reasoning and gpt-oss medium-effort, but not assumed.**
- **"Does ensemble (majority vote across 2–3 models) deliver gains?"** Mixed. The "Majority Rules" paper (arXiv 2511.15714, November 2025) shows ensembles deliver substantial F1 lift on content categorisation when models have comparable individual performance and partially independent errors. The phishing-detection ensemble study (arXiv 2412.00166) cautions that when one model dominates, ensembling does not exceed its single performance. **Practical guidance:** if the user finds two models within ~3 F1 points of each other on the gold set, a 2-of-3 majority vote is worth ~+2–4 F1 in expectation. If one model dominates by >5 F1, skip the ensemble and just use it. Independence of error modes matters more than raw count — pair Qwen3 14B (instruction-tuned dense) with gpt-oss-safeguard (MoE policy reasoner) and Phi-4-reasoning (reasoning-distilled dense) for maximum error-mode diversity.

---

## Section B: Techniques for the Quote-then-Refute Problem

The literature is unambiguous about why a single global "decide carrying or debunking" prompt fails on this pattern. The 2025 stance-detection survey (arXiv 2505.08464) catalogues this as a known failure mode: stance is context-dependent, articles can contain conflicting stance signals, and LLMs are sensitive to surface cues like quotation that they conflate with endorsement. Below are the techniques most directly applicable.

### Stance detection in news articles

The state-of-the-art for stance detection in 2024–2026 has converged on three patterns, in approximate order of accuracy gain:

1. **Fine-tuned 7B–14B models on stance-specific data** — Stance Detection on Social Media with Fine-Tuned LLMs (arXiv 2404.12171), and the "Fine-Tuned Small LLMs Outperform Zero-Shot Generative AI" paper (arXiv 2406.08660). Findings: fine-tuned 7B models consistently beat zero-shot GPT-4/Claude on stance, with sweet-spot training data between 200–500 examples and saturation around 500.
2. **Chain-of-Thought + LLM-as-encoder** — "Chain-of-Thought Embeddings for Stance Detection" (arXiv 2310.19750). Generate a CoT explanation with the LLM, then feed the explanation text into a smaller transformer encoder for the actual classification. This recovers most of the CoT benefit while avoiding "stance label hallucination" where the LLM's correct reasoning gets paired with the wrong final label — exactly the regression mode the user observed when they added a "scan for refutation" instruction.
3. **CoT prompting with task-specific decomposition** — "Investigating Chain-of-Thought with ChatGPT for Stance Detection" (arXiv 2304.03087) shows raw CoT helps, but only when decomposed into sub-questions ("who is making the claim?", "is the article author endorsing or critiquing?"). An open-ended "explain your reasoning" prompt is roughly neutral.

### Refutation detection / claim verification (FEVER, AVeriTeC)

The FEVER 2024 winners (arXiv 2410.12377 — HerO, 2nd place at AVeriTeC score 0.57; arXiv 2411.05762 — Papelo, multi-hop evidence pursuit) settled on a near-identical recipe:

1. **HyDE-style retrieval expansion** — generate hypothetical documents that would support/refute the claim, embed them, retrieve real evidence by similarity.
2. **Question generation conditioned on the claim** — for each retrieved passage, the LLM generates verification questions that decompose the claim's verifiability.
3. **Two-class reduction** — Papelo explicitly shows that *reducing the problem to two classes* (supports/refutes) at the per-evidence step, then aggregating, beats trying to predict the 4-way veracity label end-to-end. The aggregation across questions yields the 4-way verdict.
4. **Reconsideration / verdict-revision step** — both winners run a final "given all the evidence, reconsider the verdict" pass.

The takeaway for Stage 4b is direct: the user already has the article and the claim, so steps 1–2 are effectively "extract sentences mentioning or relevant to this claim." Steps 3–4 are where the win is — *a per-passage stance pass followed by an article-level aggregation step.*

### Cross-paragraph reasoning and speaker attribution

The "Speaker attribution in German parliamentary debates with QLoRA" paper (arXiv 2309.09902) shows that fine-tuning a 7B Llama-2 model with QLoRA on speaker-attribution tasks produced competitive results on a structured task very similar to "who said the misinformation claim, and is the author endorsing it?" The "Think Before You Attribute" paper (arXiv 2505.12621) introduces a sentence-level pre-attribution classifier that decides per sentence whether it is "not attributable / attributable to a single quote / attributable to multiple quotes" — exactly the granularity needed to disentangle the quote-then-refute pattern.

### Multi-hop reasoning

The "Decomposing and Revising What Language Models Generate" framework (FIDES, arXiv 2509.00765) and Papelo's multi-hop pursuit both confirm: **decomposition into per-passage decisions, then aggregation, is more robust than one-shot global classification.** The user has effectively been asking the 14B model to do an N-hop reasoning step in one prompt. Splitting it eliminates the over-correction failure mode.

### Two-pass / cascaded LLM pipelines

Recent applied work confirms that cascaded pipelines reliably beat single-pass inference on classification. "Multi-stage Large Language Model Pipelines Can Outperform GPT-4o in Relevance Assessment" (arXiv 2501.14296) reports an 18.4% Krippendorff α improvement from a multi-stage pipeline using a small LLM versus single-pass GPT-4o-mini. "Toward Reliable Clinical Coding" (arXiv 2510.07629) uses a generate–expand–verify pipeline that demonstrably catches the kind of hierarchical near-miss that a single classifier produces.

### Chain-of-Verification

Dhuliawala et al.'s CoVe (arXiv 2309.11495, ACL Findings 2024) is the canonical pattern: model drafts → model plans verification questions → model answers them *independently of the draft* → model produces the verified final answer. The independence step is critical — if you let the verification step see the draft answer, the model anchors and confirms. CoVe demonstrably reduces hallucination on Wikidata, MultiSpanQA, and longform tasks. **For Stage 4b, the directly applicable variant is: classify → independently extract passages that would refute the claim (without showing the verifier the original verdict) → re-score.** This is a much safer formulation than the user's failed "scan for refutation" prompt because the verifier is not biased by the draft.

### Why the user's prompt revision regressed

The "Mitigating Boundary Ambiguity and Inherent Bias for Text Classification" paper (arXiv 2406.07001) explains the mechanism: LLMs have token-level biases on classification options. Adding "scan for refutation" to the prompt shifted the model's prior away from `carrying` and toward `debunking`/`neutral_reporting` uniformly, regardless of evidence. This is the same reason CoVe insists on independence between the draft and the verification — and the same reason a structured decomposition (extract passages first, classify second) outperforms an instruction nudge.

### Structured prompting techniques: which actually work for stance/refutation

- **Plain CoT**: small but real gains on stance, big variance (Cambridge Political Analysis study; arXiv 2304.03087). +3–8 F1 typical.
- **Plan-and-Solve / Decomposition**: bigger and more reliable gains on multi-step classification (Multi-stage Pipelines paper).
- **Tree-of-Thought**: heavy compute, marginal gains on classification — designed for problems with branching solution spaces, not 4-way labels.
- **Self-consistency**: reliable +2–5 F1 by sampling 5–10 reasoning paths and majority-voting — but at 5–10× latency.
- **Constitutional/self-critique**: the user's failed "scan for refutation" prompt is in this family. Works only when the critique is structurally independent (CoVe-style), not when bolted onto the same prompt.

---

## Section C: Pipeline Architecture and Prompting Strategies

### C.1 Recommended Stage 4b redesign — "extract-then-classify"

The pattern with the highest expected value, and the smallest engineering cost, is:

**Pass 1 — Evidence extraction (structured, per-claim).** For each (article, claim) pair, prompt the model to emit a JSON object with:
- `claim_relevant_spans`: list of `{sentence_text, position, speaker_or_author, quoted: bool, treatment: "asserts" | "denies" | "describes" | "ambiguous"}`.
- `author_voice_summary`: 1-sentence description of the article author's framing (separate from any quoted source).
- The `evidence_quote` problem disappears here: the model must select from a list of extracted, position-tagged sentences, and post-hoc validation is a literal substring check against the article.

**Pass 2 — Stance classification (structured, conditioned on Pass 1).** Given the structured spans, prompt the model with a tight 4-way schema:
- "Given these claim-relevant passages and author-voice summary, classify the article's stance toward the claim."
- The model now sees explicitly: which sentences quoted whom, whether the author's voice asserted or refuted, and where each sentence sits in the article.

Why this beats the failed prompt revision: in Pass 1 the model is making a *factual extraction* decision per sentence (much easier, much less prior-prone). In Pass 2 it is making a *meta* decision over already-structured evidence. The "quote-then-refute" pattern surfaces naturally as a `quoted: true / treatment: asserts` span followed by a `quoted: false / treatment: denies` author-voice span — a pattern the classifier can be explicitly trained to map to `debunking`.

This is essentially the AVeriTeC HerO recipe applied to a closed-corpus problem and is the single most defensible architectural change.

### C.2 Two-pass verification (focused refutation check on `carrying` verdicts only)

Cheaper and a useful first experiment before the full extract-then-classify rebuild:

1. Run current Stage 4b unchanged.
2. **Only when the verdict is `carrying`**, run a focused second prompt that says: "List every sentence in this article (verbatim) where any speaker contests, denies, contextualises, fact-checks, or expresses doubt about the following claim. If none, output an empty list. Do not paraphrase."
3. If the list is non-empty and contains substantive language (more than "critics say" / "some argue" boilerplate — see C.3), reclassify as `debunking`.

This is a "verify when uncertain" cascade (arXiv 2502.15845). The advantage of restricting it to `carrying` verdicts is that the recall=1.00 on `carrying` means *all* the false positives are inside this set — a focused second-pass solely on this set targets the exact failure mode at minimal latency cost. Expected gain: recovers most of the 16% false-positive rate on `carrying` without touching the other classes.

### C.3 Distinguishing "critics say" boilerplate from substantive refutation

The dominant failure mode in the user's revised prompt was that the model treated *any* contrasting language as substantive refutation. The fix is structural, not prompt-engineered:

- **Length and specificity heuristic**: a substantive refutation usually contains a counter-claim or evidence (numbers, named sources, specific facts), not just a contrasting verb. A simple post-hoc rule of "refutation span must contain ≥1 entity not in the claim, OR contain a numeric value, OR be ≥2 sentences" filters out a large fraction of "critics say" tokens.
- **Speaker attribution**: refutation by the article's author voice (or by a named third-party fact-checker) counts; refutation by a partisan opposition source does not necessarily — the article may be `carrying` even with token "the other side disagrees" balancing.
- **Train this in the fine-tune** (Section D): the highest-value synthetic adversarial examples are exactly pairs where token "critics say" appears but the article still carries.

### C.4 Hallucinated quote mitigation

Three layers, deploy together:

1. **Post-hoc substring validation.** After Stage 4b emits an `evidence_quote`, verify that the quote (with normalised whitespace) is a literal substring of the article. If not, re-run the prompt with the failed quote in the system message ("Your prior answer included a quote that does not appear in the article. Re-extract.") or fall back to an empty `evidence_quote` field. This is the single highest-ROI hallucination fix and costs almost nothing.
2. **Constrained extraction at generation.** Use Outlines or llama.cpp grammar-based decoding to constrain the `evidence_quote` field to be a literal continuation of one of the article's sentences. Outlines (dottxt-ai) supports JSON schema, regex, and CFG constraints by token-masking during sampling. This guarantees correctness rather than relying on the model. Outlines integrates with Hugging Face transformers and (via llama-cpp-python) with GGUF models; it does *not* yet integrate cleanly with Ollama's HTTP server, so this is a "outside Ollama" lever.
3. **Citation-aware models (Cohere Command-R7B as evidence-extractor sub-model).** Command-R7B's grounded-generation mode is explicitly trained to emit citation spans tied to source documents. Running it as a *sub-step* — give it the article + claim, ask for the evidence span, then feed that span into Qwen3 as the classifier — is a viable architecture. The 7B size leaves plenty of headroom alongside Qwen3 14B for parallel loading. This is more architectural complexity than (1) and (2), so deploy it only if the simpler fixes don't close the gap.

### C.5 Structured-output enforcement

The state of the art on local models in 2026 is, in order of strictness:

1. **Outlines / llama.cpp GBNF grammars** (strictest) — token-level masking guarantees the output is a valid JSON conforming to the schema. Inference is slightly slower (token-mask kernel is not fully parallel on GPU) but the error rate from malformed JSON is zero. Best for the Stage 3.5 long-context structured-output fragility issue.
2. **Ollama structured outputs** (Pydantic / Zod schema → `format` parameter, available since Ollama 0.5) — internally generates a GBNF grammar from the schema and passes it to llama.cpp. Easier to use; equivalent guarantees as Outlines for JSON; slightly less flexibility for non-JSON formats. Documented best practice: include the schema in the prompt as well as in `format=`, and set `temperature=0`. **This is a free upgrade over the user's current Stage 3.5 / Stage 4b extraction. Deploy immediately.**
3. **Instructor library** with Pydantic + retries — works on top of Ollama, layers automatic validation and retry-with-error-message logic. Lower guarantee than (1) and (2) but useful when you want validation logic Pydantic-side (custom validators, etc.).
4. **Function calling** — Qwen3, gpt-oss, Mistral 3.2, and Llama 3+ all support function calling natively in Ollama; the response is constrained to the function signature. Useful for the verdict + evidence_quote shape.

For Stage 3.5 (claim normalisation/clustering, the documented "structured-output fragility under long-context pressure" issue), switching from prompt-based JSON to Ollama's `format=` schema will eliminate the JSON-shape failure mode entirely. The only remaining failure will be missing semantic fields (the model omits a real claim) — which is a quality issue, not a structure issue.

### C.6 Embedding model upgrades for Stage 4a

The user's current `nomic-embed-text` (137M, 8192 ctx) is solid for general retrieval but the recent benchmarks show it underperforming on harder retrieval tasks. April 2026 evidence:

| Embedding model | MTEB avg | Long-doc (8K) | Notes |
|---|---|---|---|
| nomic-embed-text v1.5 | 62.4 | 0.40–0.44 (degrades sharply ≥4K) | Current baseline. |
| **nomic-embed-text-v2-moe** | ~64 | 0.92 at 8K | MoE successor; same Ollama-friendly footprint. **Drop-in upgrade.** |
| **bge-large-en-v1.5** | 64.0 | 512 ctx (limit) | Best classification (75.5) and STS (83.1) per MTEB. Short context is a problem for whole-article embedding. |
| **bge-m3** | ~66 | Strong | Multilingual + dense + sparse + multi-vector in one model; #1 in Tiger Data RAG retrieval study (72% accuracy vs 57% for nomic). |
| **mxbai-embed-large-v1** | 64.7 | 512 ctx | Strong on English MRL but short context. |
| **jina-embeddings-v3** | 65.5 | 8192 ctx (RoPE-based, demonstrably best in class) | 570M params, task-specific LoRA adapters (`retrieval.query` / `retrieval.passage` / `classification` / `text-matching`). On the FEVER benchmark Jina-reranker-v3 hits 93.95 — **this family is explicitly trained on fact-verification retrieval**. |
| **e5-mistral-7b-instruct** | 66.6 | 4096 | Top retrieval scores but 7B-class size — adds ~5 GB on top of Qwen3, not viable alongside the LLM at parallel=4. |

**Recommendation:** swap to `jina-embeddings-v3` with `retrieval.passage` adapter for indexing and `retrieval.query` for claim queries. The fact-verification specialisation is directly relevant, the 8K context is sufficient, and the model is small enough (570M) that it sits comfortably alongside Qwen3 14B in VRAM. Second choice: `bge-m3` if the user needs hybrid dense+sparse retrieval. Third choice (drop-in, low risk): `nomic-embed-text-v2-moe`.

The user should also consider that embedding-retrieval false matches are forcing Stage 4b to classify topically-similar but irrelevant pairs into `irrelevant`. A reranker step (Jina-reranker-v3, 0.6B, listwise) between Stage 4a retrieval and Stage 4b classification will reduce these false-match-derived classification errors substantially. This is a separate intervention from upgrading the embedder and is additive.

---

## Section D: Fine-tuning Walkthrough (First-time)

This is the highest-expected-value single intervention for the user's specific failure mode. Published evidence:

- **Sweet spot is 200–500 well-curated examples**, with saturation around 500 and diminishing returns past ~5K (Kaddour & Liu, "Synthetic Data Generation in Low-Resource Settings", arXiv 2310.01119; Bertz et al. "Fine-Tuning LLMs on Small Medical Datasets", arXiv 2503.21349; Oliver & Wang, arXiv 2407.13906 — fine-tuning with 200 samples improved accuracy from 70 → 88% on a product-extraction task).
- **A 14B-class fine-tune with 500 stance examples typically delivers +10–20 F1 over the zero-shot baseline** (Wang et al. on failure mode classification, arXiv 2309.08181, GPT-3.5 fine-tune F1 0.46→0.80 with several hundred examples; "Fine-Tuned Small LLMs Outperform Zero-Shot Generative AI", arXiv 2406.08660, fine-tuned 7B-class beats zero-shot Claude Opus on stance classification).
- The user's current 90% accuracy ceiling is not the natural ceiling for this task — it is the zero-shot ceiling for Qwen3 14B *without* learned distinctions for the quote-then-refute pattern. Targeted fine-tuning is the right tool.

### D.1 Tooling decision: Unsloth (recommended for first-time)

The 2025–2026 consensus (Modal, Spheron, Hyperbolic comparison guides) is that **Unsloth is the right starting point** for a single-GPU fine-tune on a 16 GB card:

- 70% less VRAM than the HuggingFace baseline at equivalent quality.
- 2× faster training.
- Single Colab/notebook flow from data → trained adapter → merged GGUF → Ollama tag.
- Native QLoRA support for Qwen3, Phi-4, Gemma 3, Llama 3, Mistral.
- Free Colab notebooks for **Qwen3 14B fine-tuning that fit on a Tesla T4 (16 GB)** — i.e., directly maps to the user's RTX 4080.

Axolotl is the better choice once the user wants multi-GPU or YAML-config-driven workflows; Torchtune is the cleanest PyTorch-native option but more boilerplate for a first run. **Use Unsloth for the first fine-tune.** Migrate to Axolotl later if/when scale demands it.

### D.2 Base model choice for fine-tuning

Pick one base model, fine-tune it, and only ablate a second if the first underperforms.

- **First choice: Qwen3 14B (base, not 2507 instruct).** It is the user's existing production model, so the fine-tune is a true delta. Strong reasoning + instruction-following baseline. Unsloth has a maintained Colab notebook for Qwen3 14B QLoRA.
- **Backup: Phi-4 14B (base).** If you want to test whether reasoning-distilled models fine-tune better on this task. Microsoft Phi-4 is 14B dense and Unsloth-supported.
- **Avoid for the first run:** Phi-4-reasoning, DeepSeek-R1-distill, gpt-oss — these are post-trained for reasoning chains, and fine-tuning them on short classification labels can degrade their reasoning behaviour in unpredictable ways. Stick to instruction-tuned bases.

### D.3 Data-scale plan

The user has 100 labelled gold rows and could expand to ~500. The recommended plan:

1. **Hold the 100 gold rows out as a strict test set.** Never train on them.
2. **Hand-label 300–500 additional rows from the production stream** (or unused articles). Stratify by class to maintain the gold-set distribution. Aim for ~30% `carrying`, 25% `debunking`, 25% `neutral_reporting`, 20% `irrelevant`.
3. **Generate ~1,500 synthetic adversarial examples with Claude Opus** focused on the quote-then-refute failure mode (recipe in D.4).
4. **Total training set: ~2,000 examples.** Within the band where small-model classification fine-tunes saturate; Kaddour & Liu and similar studies show synthetic + real beats real-only at this scale.
5. **Validation set: 10–15% of the 2,000, stratified, used for early stopping.**

Below 500 total examples, fine-tuning will help but may not generalise robustly to the quote-then-refute pattern; above 5,000, gains saturate and labelling effort is wasted. The 2,000 mid-point is well-supported by published evidence.

### D.4 Synthetic data generation recipe

Use Claude Opus (the same model that labelled the gold set, for label consistency). Generate examples that target the documented failure mode. Suggested prompt skeleton:

```
You will generate synthetic training examples for a misinformation
classifier. Each example has an article, a claim, and a verdict
(carrying / debunking / neutral_reporting / irrelevant).

Generate a {VERDICT_CLASS} example with this structural pattern:
- The article quotes a source asserting the claim verbatim.
- {Then either: the article author rebuts the claim with evidence in
  the next paragraph (debunking) | the article includes only "critics
  say" boilerplate without substantive rebuttal (carrying) | etc.}

Constraints:
- 4-8 paragraphs, 250-500 words.
- Realistic news prose — no labels or hints in the article text.
- The author-voice paragraphs should use {specific named entities,
  numbers, dated events} when refuting; use vague balancing language
  ("critics say", "some argue") when not refuting.

Output JSON: {"article": ..., "claim": ..., "verdict": ...,
"evidence_quote": ..., "rationale": ...}
```

Two strong heuristics from the synthetic-data-for-classification literature ("Better as Generators Than Classifiers" arXiv 2601.16278; "From Measurement Instruments to Data" arXiv 2410.12622):

1. **Vary structural patterns explicitly in the generation prompt** — don't trust the model to generate diverse patterns on its own. Iterate over: quote-first-rebut-after, rebut-first-quote-after, multiple quoted sources with one refuting and one supporting, quoted source + author neutral, long article with refutation buried in paragraph 5, etc.
2. **Generate ~3× as many `carrying` and `debunking` examples as `neutral_reporting` and `irrelevant`.** These are the harder classes for the model.

Validate a 10% sample of the synthetic data by hand. If Claude's verdicts disagree with your judgement on >5% of synthetic examples, the synthetic distribution is biased — re-run with a stricter spec. (You can also have Claude produce a rationale and then *re-classify* its own example without the rationale, to filter out cases where Claude itself is uncertain.)

### D.5 End-to-end Unsloth walkthrough

Approximate notebook outline (works on RTX 4080 16 GB):

```python
# 1. Install
!pip install -U "unsloth @ git+https://github.com/unslothai/unsloth.git"
!pip install --no-deps "trl<0.9" "peft<0.13" "accelerate" "bitsandbytes"

# 2. Load Qwen3 14B in 4-bit
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/Qwen3-14B",  # base, not 2507
    max_seq_length = 2048,             # keep small for first run
    dtype = None,
    load_in_4bit = True,
)

# 3. Add LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,                    # rank; 16 is the standard starting point
    target_modules = ["q_proj","k_proj","v_proj","o_proj",
                      "gate_proj","up_proj","down_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
)

# 4. Format the dataset to chat template
def format_example(ex):
    return {"text": tokenizer.apply_chat_template([
        {"role":"system","content": SYSTEM_PROMPT_FOR_4B},
        {"role":"user","content": f"ARTICLE:\n{ex['article']}\n\n"
                                  f"CLAIM:\n{ex['claim']}\n\n"
                                  f"Classify."},
        {"role":"assistant","content": json.dumps({
            "verdict": ex["verdict"],
            "evidence_quote": ex["evidence_quote"],
            "rationale": ex["rationale"],
        })},
    ], tokenize=False)}

# 5. Train
from trl import SFTTrainer
from transformers import TrainingArguments
trainer = SFTTrainer(
    model = model, tokenizer = tokenizer,
    train_dataset = train_ds, eval_dataset = val_ds,
    dataset_text_field = "text", max_seq_length = 2048,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,    # effective batch = 8
        warmup_steps = 10,
        num_train_epochs = 3,                # start with 3, watch eval
        learning_rate = 2e-4,
        fp16 = True,
        logging_steps = 10,
        eval_strategy = "steps", eval_steps = 50,
        save_strategy = "steps", save_steps = 50,
        load_best_model_at_end = True,
        output_dir = "outputs",
    ),
)
trainer.train()

# 6. Save merged 16-bit, then export GGUF Q4_K_M for Ollama
model.save_pretrained_merged("qwen3-14b-stage4b-merged",
                             tokenizer, save_method="merged_16bit")
model.save_pretrained_gguf("qwen3-14b-stage4b-gguf",
                           tokenizer, quantization_method="q4_k_m")

# 7. Register with Ollama
# Modelfile:
#   FROM ./qwen3-14b-stage4b-gguf/unsloth.Q4_K_M.gguf
#   TEMPLATE """{{ .System }}\n{{ .Prompt }}"""
#   PARAMETER num_ctx 8192
#   PARAMETER temperature 0
# Then:
#   ollama create qwen3-14b-stage4b -f Modelfile
```

### D.6 Evaluation and stopping criteria

- **Train/val/test split**: 80% train, 15% val (synthetic + real, mixed), 5% real held-out. **Plus** the 100-row gold set as a final, untouched test set.
- **Watch the eval loss curve.** Early stopping when val loss plateaus for 2 evaluation steps. Three epochs is usually right for 2K examples; small datasets overfit fast at higher LR.
- **Run `gold_set_eval.py` after every checkpoint** — your existing harness is the source of truth, not the eval loss.
- **Stop training when the gold-set F1 stops improving.** Catastrophic forgetting on adjacent skills (Stage 1, Stage 2, Stage 3.5) is a real concern with LoRA — verify on a sample of those after the run. The arXiv 2401.05605 study documents catastrophic forgetting even in LoRA fine-tuning, so spot-check.

### D.7 Realistic accuracy expectations

Conservative published-precedent estimates for a 14B-class QLoRA fine-tune with ~2,000 stance examples:

- **+5–10 overall accuracy points** on the gold set is a defensible base case (90% → 95–96%).
- **Larger gain on the specific failure class** — `carrying` precision should rise from 0.84 toward 0.90+ as the model learns the quote-then-refute pattern explicitly.
- **+2–4 F1 on `irrelevant` recall** as the model learns to distinguish topically-similar-but-irrelevant pairs (helping Stage 4b absorb embedding false matches more gracefully).
- **`evidence_quote` hallucination rate should fall** since the fine-tune teaches the model to select from article spans, but combine this with the post-hoc substring check (C.4) for guarantees.

If the fine-tune underperforms (delta <2 F1), the most likely causes are: (1) synthetic data distribution doesn't match real distribution — increase real:synthetic ratio; (2) base model is underpowered — try Phi-4 14B as the base; (3) dataset too small — expand real labels to 500.

---

## Section E: Direct Answers to Specific Open Questions

These are summarised from the per-section discussion above:

**Q1: Does Qwen3:32B at Q3/Q2 preserve enough quality?**
No. The empirical Qwen3 quantisation study and the long-context quantisation study both show ultra-low-bit (2–3 bit) hurts linguistic and especially long-context tasks disproportionately, and the user's task is a long-context multi-paragraph attribution problem. A Q4 14B fine-tune is a strictly better use of the same budget. Skip Q3/Q2 32B.

**Q2: Can Phi-4:14b match or exceed Qwen3:14b on classification/stance?**
Plausibly yes on reasoning-heavy decisions (Phi-4-reasoning beats DeepSeek-R1-Distill-70B on reasoning benchmarks despite being 5× smaller), plausibly no on instruction-following polish where Qwen3 14B is the stronger generalist. The right answer is empirical — include both in the benchmark sweep. The quote-then-refute problem is reasoning-heavy, which favours Phi-4-reasoning, but raw instruction adherence under JSON-schema constraints favours Qwen3.

**Q3: Is reasoning mode actually more accurate on classification despite the 5–10× latency?**
Modest gains expected — published evidence (arXiv 2509.13332) shows Qwen3 thinking mode delivers +10.5 points on judge tasks at only 1.82× FLOPs versus 7-shot ICL (+4.5 points at 8.16× FLOPs), so reasoning is more cost-efficient than few-shot prompting. But returns saturate around 256–512 reasoning tokens. For a 4-way classification with structured input, expect a few F1 points of gain at 5–10× output-token cost. Worth testing on the gold set; not assumed worth the latency in production unless the latency is acceptable.

**Q4: Does ensemble (majority vote across 2–3 local models) deliver gains?**
Conditionally yes. Gains require comparable individual performance (gap <5 F1) and partially independent error modes. Pair Qwen3 14B with gpt-oss-safeguard-20b and Phi-4-reasoning for maximum architectural and training-data diversity. Typical published gain in this regime: +2–4 F1. If one model dominates on the gold set, skip the ensemble — its compute is better spent on the fine-tune.

---

## Recommended Action Plan (in priority order)

1. **Immediate (this week)** — Adopt Ollama structured outputs (`format=` schema) for Stage 3.5 and Stage 4b, and add the post-hoc substring validator for `evidence_quote`. Zero-cost robustness improvements.
2. **Short term (1–2 weeks)** — Run the gold-set sweep across the Section A shortlist (Qwen3 14B baseline, gpt-oss-safeguard-20b, Phi-4-reasoning 14B, Gemma 3 12B, Mistral Small 3.2 24B at parallel=2, gpt-oss-20b, DeepSeek-R1-distill-Qwen-14B, optionally Qwen3.5 9B). Record accuracy and per-class F1 with `gold_set_eval.py`. Test reasoning-on vs reasoning-off where applicable.
3. **Short term (1–2 weeks, parallel)** — Implement the focused-second-pass `carrying` verifier (Section C.2). Expected ~+3–5 accuracy points at small additional latency.
4. **Medium term (3–4 weeks)** — Rebuild Stage 4b as extract-then-classify (Section C.1). The largest architectural gain.
5. **Medium term (3–4 weeks, parallel)** — Expand labelled set to 500 real, generate 1,500 synthetic adversarial examples, run Unsloth QLoRA fine-tune on Qwen3 14B per Section D walkthrough. Compare against best zero-shot baseline from step 2.
6. **Optional (later)** — Swap embedder to `jina-embeddings-v3`; add a reranker (Jina-reranker-v3); explore Command-R7B as a citation-aware sub-step for `evidence_quote` extraction.

The single highest-expected-value intervention, conditional on the gold-set sweep not turning up a model that already solves the problem, is the fine-tune — it directly attacks the quote-then-refute failure mode in a way that prompt engineering provably cannot. The decomposition rebuild is a close second and is more durable across model upgrades. Do both; they compound.