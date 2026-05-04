# Multi-Domain Misinformation Tracker — Scope Expansion Plan

**Status**: Draft for review. Last updated 2026-05-03.

This document scopes the expansion from a single-domain (women's health) misinfo detection pipeline into a multi-domain platform producing per-domain reports plus a roll-up summary across five domains:

1. **Health / medicine** (currently: women's health — being finalized in Phase A.5)
2. **Elections / politics** (focus: elections & voting)
3. **Climate / environment** (focus topic TBD — proposals below)
4. **War / foreign policy** (focus topic TBD — scope choice required, see below)
5. **Immigration / crime** (focus topic TBD — proposals below)

Each domain gets a standalone `FINDINGS.md` and PBI dataset. A roll-up layer combines them for cross-domain analysis (outlets carrying across multiple domains, ideological correlations, time-series).

---

## Effort estimate

| Phase | Work | Est. wall time | Sessions |
|---|---|---|---|
| **A.5** | Finish women's health complete (SRHR collection + 8-yr window + topic gate 0.65 + re-run) | 6–10 hr | 1 (in progress) |
| **A.75** | Architecture refactor — `--domain` flag through every pipeline script; migrate women's health into `data/domains/womens_health/` | 4–6 hr | 1 |
| **B** | Elections / politics domain | 6–10 hr | 1–2 |
| **C** | Climate / environment domain | 6–10 hr | 1–2 |
| **D** | War / foreign policy domain | 6–10 hr | 1–2 |
| **E** | Immigration / crime domain | 6–10 hr | 1–2 |
| **F** | Roll-up report + cross-domain analysis | 5–10 hr | 1 |
| **Total** | | **40–70 hr** | **~7–10 sessions** |

The bottleneck on each domain run is the article scrape (HTTP-bound, hard to parallelize beyond ~5 threads without triggering Cloudflare blocks) and Stage 4b LLM verification (~0.5 pairs/s on gpt-oss-safeguard). Per-domain LLM cost is approximately zero (local Ollama). Per-domain Anthropic API cost (gold-set re-judging if we validate per-domain): ~$10/domain, optional.

---

## Architectural changes

### Current state

Hardcoded single-domain paths everywhere:
- `data/womens_health_articles.csv` (Stage 0 input)
- `data/articles_classified.csv`, `data/claims.json`, `data/stage4b_verdicts.json` (intermediate)
- `data/misinfo_carriers.csv`, `data/misinfo_carriers_by_article.csv`, `docs/FINDINGS.md` (Stage 5)

Single query script: `pipeline/queries_public_collection_womens_health.py`.

### Target state

```
pipeline/
  domains/
    womens_health/
      queries.py                     # MediaCloud query terms + collection IDs
      external_factcheck_terms.py    # Google Fact Check API queries
      ideology_overrides.py          # optional per-domain outlet ideology overrides
    elections/...
    climate/...
    war_foreign_policy/...
    immigration_crime/...
  stage0_preprocess.py               # all stages take --domain <name>
  stage1_classify.py
  stage2_claim_extractor.py
  stage3_filter.py
  stage3_5_normalize.py
  stage4a_retrieval.py
  stage4b_verify.py
  stage5_report.py
  stage5_pbi_export.py
  rollup_report.py                   # NEW — combines verdicts across domains
  rollup_pbi_export.py               # NEW

data/
  domains/
    womens_health/
      raw_articles.csv               # MediaCloud query output
      articles_text.csv              # post-scrape
      articles_classified.csv        # Stage 1 output
      claims.json                    # Stage 2
      claims_verified.json           # Stage 3
      claim_families_filtered.json   # Stage 3.5
      stage4a_candidates.json        # Stage 4a
      embeddings_*.npy               # Stage 4a
      stage4b_verdicts.json          # Stage 4b
      misinfo_carriers.csv           # Stage 5
      misinfo_carriers_by_article.csv
      misinfo_carriers_pbi.csv
      misinfo_carriers_spot_check.csv
      external_factchecks_claims.json
    elections/... (same shape)
    ...
  rollup/
    all_verdicts.csv                 # union across domains
    cross_domain_outlets.csv         # outlets carrying ≥N domains
    domain_comparison.csv            # per-domain summary stats

docs/
  findings/
    womens_health.md
    elections.md
    climate.md
    war_foreign_policy.md
    immigration_crime.md
    ROLLUP.md
```

### Refactoring effort

Per-script changes:
- Add `--domain <name>` argparse flag
- Resolve all data paths via a `data_dir(domain)` helper
- Per-domain `queries.py` imported dynamically
- Same for `external_factcheck_terms.py`

`pipeline/stage5_report.py` already supports CLI args for input/output files — extending it is mostly path-rewiring.

`pipeline/stage4b_verify.py` is already model-configurable via `STAGE4B_MODEL` env var; no model-tier change needed for the refactor.

Migration step: re-run women's health under the new structure to confirm output parity with the current single-domain run, then delete the old hardcoded paths.

**Risk**: refactor breaks the working pipeline. Mitigation — keep women's health Phase A.5 output frozen as ground truth; refactored pipeline must reproduce it.

---

## Per-domain specifications

### Domain 1: Health / medicine — women's health (current)

**Status**: Phase A.5 in progress (SRHR collection added, window widened to 2018-06-24, topic gate 0.65).

**Carrier-vocabulary topics** (existing 10):
- abortion pill reversal
- chemical abortion harms
- emergency contraception abortifacient
- birth control harm claims
- IUD misinfo
- mifepristone safety attack
- fertility awareness superiority
- CPC promotion
- trad wife anti-contraception
- wellness hormone influencers

**MediaCloud collections**:
- `34412234` US National Top Online (248)
- `8878332` Sexual and Reproductive Health and Rights (2,524)

**External fact-check seed queries**: morning after pill, emergency contraception, IUD, birth control, contraception, fertility awareness, crisis pregnancy center, Project 2025 abortion (already in `pipeline/external_factchecks.py` `--default-queries`).

**Date window**: 2018-06-24 → today.

**Open follow-ups within domain**:
- Maybe add carrier-vocabulary queries: `"abortion regret"`, `"post-abortion syndrome"`, `"abortion drug deaths"`
- Future: per-state misinfo (Texas SB8 era, post-Dobbs trigger laws)

### Domain 2: Elections / politics

**Carrier-vocabulary topics** (proposed — review):
- **2020 election fraud claims**: `"rigged election"`, `"stolen election"`, `"voter fraud"`, `"Dominion voting machines"`, `"Sharpiegate"`, `"ballot harvesting"`, `"mail-in fraud"`, `"dead voters voting"`, `"election integrity"`
- **2024 election claims**: `"non-citizen voting"`, `"illegal alien voting"`, `"ballot stuffing"`, `"vote flipping"`, `"machine-assisted fraud"`
- **General**: `"voter suppression"` (carrier framing), `"voter ID fraud"`, `"election denial"` (← debunker vocabulary; **drop**)
- **Specific viral claims**: `"2000 Mules"`, `"Hugo Chavez voting"`, `"Italygate"`, `"Hammer and Scorecard"`

**Date window proposal**: 2018-01-01 → today (covers 2020 cycle pre-election + post-claims era + 2024 cycle).

**MediaCloud collections**:
- `34412234` US National Top Online (248)
- `8875111` US Political Blogs - Conservative (298)
- `8875109` US Political Blogs - Liberal (201)
- `262985243` US Most Visited Right (11)
- `262985242` US Most Visited Left (23)

**External fact-check seed queries**: "election fraud", "voter fraud", "Dominion voting", "ballot harvesting", "mail-in voting", "2020 election", "election integrity"

**Decisions needed**:
- Confirm topic list (which to add/drop)
- Confirm date window
- Whether to include 2008-2016 election content for longitudinal comparison

### Domain 3: Climate / environment (focus TBD)

**Possible carrier-vocabulary topics** (review and pick):
- **Denial framings**: `"climate hoax"`, `"global warming hoax"`, `"climate alarmism"`, `"climate cult"`, `"warming is natural"`, `"CO2 is plant food"`, `"ice age coming"`, `"hockey stick fraud"`, `"Climategate"`
- **Net-zero attacks**: `"Net Zero will starve"`, `"Net Zero impossible"`, `"green energy disaster"`, `"green new deal communism"`
- **EV / renewables FUD**: `"EV batteries explode"`, `"EV fires"`, `"wind turbine fires"`, `"wind turbines kill birds"`, `"solar panels toxic"`, `"solar farm wildlife"`
- **15-min cities conspiracy**: `"15 minute cities"` (with conspiracy framing — needs NOT-clauses to exclude urban-planning coverage)
- **Weather manipulation**: `"weather manipulation"`, `"geoengineering"`, `"chemtrails"`, `"HAARP"`, `"cloud seeding lawsuit"`

**Date window proposal**: 2018-01-01 → today (covers IRA, Inflation Reduction Act, EV tax credits, multiple climate summits).

**MediaCloud collections**:
- `34412234` US National Top Online
- `8875111` Conservative Political Blogs (where most carriers concentrate)
- `262985243` US Most Visited Right
- (consider an environment-specific collection if MediaCloud has one — research needed)

**External fact-check seed queries**: "climate hoax", "global warming", "Net Zero", "EV battery", "wind turbine", "15 minute cities", "geoengineering", "chemtrails"

**Decisions needed**:
- Focus topic — pick a primary thread (climate-denial, renewables-FUD, 15-min cities) or pursue all three?
- Date window confirmation

### Domain 4: War / foreign policy (focus TBD)

⚠ **High political sensitivity**. Need explicit scope decision.

**Sub-domain options** (pick one, two, or all):

**Option A — Russia/Ukraine**:
- `"Ukraine biolabs"`, `"NATO provoked"`, `"Zelensky cocaine"`, `"Zelensky Nazi"`, `"Ukraine Nazi"`, `"Azov battalion"`, `"Hunter Biden Ukraine"`, `"Crimea coup"`, `"Bucha staged"`

**Option B — Israel/Gaza**:
- `"Hamas hospitals"`, `"Israel false flag"`, `"crisis actors Gaza"`, `"Pallywood"`, `"Al-Shifa weapons"`, `"hostage staging"`, `"Israel kills journalists"` (← could be either side; needs NOT-clauses)

**Option C — Iran/China**:
- `"Iran nuclear lies"`, `"Iran terror"`, `"China bioweapon"`, `"China Wuhan lab"`, `"China spy balloon"`, `"China stole election"`

**Date window proposal**: depends on sub-domain (Ukraine: 2022 onward; Israel/Gaza: 2023 onward; Iran/China: longer span).

**MediaCloud collections**:
- `34412234` US National Top Online
- `8875111`/`8875109` Political blogs (both ideologies)
- (research foreign-policy-specific collections)

**External fact-check seed queries**: per sub-domain, e.g. "Ukraine biolabs", "Bucha staged", "Hamas hospitals", "Pallywood", etc.

**Decisions needed**:
- Sub-domain scope (A, B, C, or combination)
- Date window per sub-domain
- Whether to treat as one domain or split into multiple

### Domain 5: Immigration / crime (focus TBD)

**Possible carrier-vocabulary topics**:
- **Immigration framings**: `"border invasion"`, `"open borders"`, `"illegal alien voting"`, `"sanctuary city"` + harms, `"caravan crisis"`, `"great replacement"`
- **Specific viral claims**: `"Springfield Haitians"` (eating pets), `"Aurora gangs"` (Tren de Aragua takeover), `"Whitmer fednapping"` (← debunker; drop), `"Kate Steinle"` (older but recurring)
- **Crime framings**: `"migrant crime wave"`, `"fentanyl border"`, `"cartels crossing"`, `"sex trafficking border"`
- **Identity / DEI**: `"DEI hire"`, `"DEI killed"`, `"woke crime"`, `"soros prosecutors"`

**Date window proposal**: 2016-01-01 → today (covers Trump 1.0 + Biden + Trump 2.0 immigration cycles).

**MediaCloud collections**:
- `34412234` US National Top Online
- `8875111` Conservative Political Blogs (high concentration)
- `262985243` Most Visited Right
- `8875109` Liberal Political Blogs (for symmetric coverage; some left-side claims exist)

**External fact-check seed queries**: "border invasion", "migrant crime", "illegal voting", "Springfield Haitians", "Tren de Aragua", "fentanyl border", "DEI hire"

**Decisions needed**:
- Focus topic — pick immigration-only, crime-only, or combined
- Whether to include domestic crime (urban crime statistics, ATF/gun, fentanyl) or only immigration-adjacent
- Date window confirmation

---

## Roll-up layer (Phase F)

### Outputs

- **`data/rollup/all_verdicts.csv`** — union of all per-domain `stage4b_verdicts.json`, with a `domain` column added. ~5K-15K rows expected total.
- **`data/rollup/cross_domain_outlets.csv`** — outlets that carry misinfo across ≥N domains. Columns: outlet, domains_carried, ideology, total_carrier_verdicts, max_per_domain. Most useful for "X is a serial misinfo carrier" framing.
- **`data/rollup/domain_comparison.csv`** — per-domain summary: total articles, total carriers, carrier rate, top 5 outlets, top 3 carrier campaigns.
- **`docs/findings/ROLLUP.md`** — narrative roll-up. Cross-domain story.

### Roll-up analyses

- **Outlet concentration**: how many outlets carry across multiple domains? Breakdown by ideology bucket.
- **Domain comparison**: carrier rate (% of total verdicts) by domain. Which domains are most polluted?
- **Time series alignment**: how do carriers cluster around major events (Roe overturn, Jan 6, Oct 7, IRA passage, election cycles)?
- **Campaign reuse**: which originating actors appear across domains? (e.g., is Heritage Foundation cited as a debunked source in both health AND elections?)
- **Ideology asymmetry**: at the per-domain level, does the carrier ideology distribution match the corpus ideology distribution? Or is it skewed?

### Open question for roll-up

How to weight carriers across domains for the "most polluted outlet" ranking — by raw count, by per-article rate within outlet, or by topic-coverage breadth?

---

## Risk register

1. **Scrape time blowout**: SRHR collection alone is 10× sources. Pre-Roe time window is 2× temporal range. With multiple domains running, total scrape time could reach 30–50 hours across all domains. Mitigation: parallelize across domain pipelines (different processes, same Linux box); accept that some domains run overnight.

2. **Cloudflare blocks getting worse**: more outlets, more articles, more chances of trip-ups. Current pipeline silently fails on Cloudflare-blocked sites. The corpus loss isn't catastrophic but could become noticeable. Mitigation: measure scrape failure rate per-domain; if >25%, invest in `curl_cffi` or `playwright` (BACKLOG item).

3. **Verifier accuracy drift across domains**: gpt-oss-safeguard was validated only on women's-health gold set. For elections/climate/war/immigration we're flying blind on accuracy until we re-judge with cloud LLM per-domain. Mitigation: per-domain ~100-row gold set + cloud judge ($10–15 each). Treat as required for credible per-domain reports.

4. **Defamation/legal exposure scales with claim volume**: 67 named outlets in women's health × 5 domains = potentially 200-400 outlet/claim publishings. Higher chance of one being wrong, lower margin for error. Mitigation: every published carrier list goes through manual spot-check via `misinfo_carriers_spot_check.csv`.

5. **Politically charged subjects across all domains**: war/foreign policy and immigration in particular. Mitigation: lead all framing with method, not findings; show carrier-vocabulary methodology before naming outlets; accept that some negative reception is inevitable.

6. **Ollama instance contention**: bigdoggie may be shared with other workloads. Pipeline runs assume the GPU is available. Mitigation: confirm GPU availability before kicking off long runs; document expected runtimes in `CLAUDE.md`.

7. **Architectural refactor regression**: rewriting pipeline path-handling could break the working women's health pipeline. Mitigation: hold Phase A.5 output as frozen ground truth; refactored pipeline must reproduce it bit-for-bit.

---

## Decisions needed (revise this section)

Before kicking off Phase B and beyond:

- [ ] **Phase A.5 sign-off**: review women's health post-rerun output before proceeding with refactor.
- [ ] **Architecture refactor commitment**: Phase A.75 takes 4-6 hr and requires full pipeline re-validation. Worth it vs. running domains via separate copies of the pipeline?
- [ ] **Elections domain (B)**: confirm topic list, confirm 2018-01-01 → today window.
- [ ] **Climate domain (C)**: pick focus thread (denial / renewables-FUD / 15-min cities / all).
- [ ] **War/foreign policy domain (D)**: pick sub-domain(s) (Russia/Ukraine, Israel/Gaza, Iran/China, or combination). Highest political risk — explicit scope choice required.
- [ ] **Immigration/crime domain (E)**: pick focus (immigration only / combined with crime / scope to specific viral claims).
- [ ] **Per-domain gold-set validation**: do we re-judge a 100-row gold set per domain (~$10-15 each) for credibility, or accept gpt-oss-safeguard's women's-health-validated numbers as a proxy?
- [ ] **Roll-up framing**: is the headline "outlets carrying across domains" (network analysis) or "domains compared" (rate comparison)? Drives the visualization design.
- [ ] **Publication strategy**: separate blog post per domain, one mega-post, or a series? Drives writing time and SEO architecture.

---

## Notes

- **Reuse principle**: every domain uses the same pipeline architecture. Stage 4b verifier is gpt-oss-safeguard for all (validated on women's health; reasonable to assume similar precision profile across domains, but per-domain gold-set validation is the right way to confirm).
- **External fact-checks**: Google Fact Check Tools API is domain-agnostic. Same `pipeline/external_factchecks.py` script with different `--query` terms feeds each domain's claim universe.
- **Ideology tagging**: `pipeline/source_ideology_tagger.py` is a hardcoded outlet→ideology map. Currently focused on US press. May need to expand for war/foreign policy domain (international outlets) and election domain (alt-press, partisan blogs).
- **Power BI**: roll-up dashboard might benefit from a sixth top-level filter on `domain`. Per-domain dashboards likely reuse the existing Power BI structure (carriers + all-verdicts tables).
