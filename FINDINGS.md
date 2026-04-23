# Misinformation Carrier Findings

Output of the cross-reference misinformation detection pipeline run against a women's-health news corpus.

## Summary

- **117 carrying verdicts** flagged across **65 unique articles**.
- Each flagged article presents a previously-debunked claim as fact, without acknowledging the debunking.
- Every flag carries provenance: the originating actor, the fact-check that debunked it, the specific passage in the article, and the LLM's reasoning.

## Methodology

1. **Corpus** — 1,486 articles pulled from MediaCloud across 10 carrier-focused topic queries (abortion-pill reversal, chemical-abortion harms, EC-as-abortifacient, IUD misinfo, mifepristone safety attacks, fertility-awareness superiority, CPC promotion, trad-wife anti-contraception, wellness-influencer hormone misinfo, generalized birth-control harm claims). Scraped with `trafilatura`. 1,159 passed eligibility (word count + topic-context gate).
2. **Stage 1 — article classification** (`qwen3:14b`): 942 ORIGINAL, 83 FACT_CHECK, 15 OTHER, 119 unclassified.
3. **Stage 2 — claim extraction** from the 83 FACT_CHECK articles: 220 debunked claims with named originators.
4. **Stage 3 — ideology cross-reference**: claims promoted to canonical only if (a) debunked by outlets across ≥2 different ideology buckets, or (b) debunked by an authoritative-solo outlet (factcheck.org, scientificamerican, npr, cbsnews, theguardian, wired, usatoday, latimes). 17 multi-ideology + auth-solo expansions.
5. **Stage 4a — embedding retrieval** with `nomic-embed-text`: 942 articles × 85 unique claim-texts, top-3 candidates per article above cosine similarity 0.65.
6. **Stage 4b — LLM verification** (`qwen3:14b`): each candidate (article, claim) pair classified as `carrying`, `debunking`, `neutral_reporting`, or `irrelevant`.

**Posture**: temperature=0, allowed-abstention output, no LLM call without grounded prior fact-check evidence.

## Carrier outlets

| Outlet | Carrier verdicts | Unique articles |
|---|---:|---:|
| ncregister.com | 22 | 14 |
| townhall.com | 17 | 10 |
| breitbart.com | 17 | 6 |
| dailysignal.com | 15 | 10 |
| dailycaller.com | 15 | 8 |
| foxnews.com | 12 | 5 |
| redstate.com | 7 | 3 |
| pjmedia.com | 6 | 4 |
| patriotpost.us | 2 | 2 |
| denverpost.com | 2 | 1 |
| spectator.org | 1 | 1 |
| vox.com | 1 | 1 |

## Campaigns being amplified

| Originating actor | Carrier verdicts | Description |
|---|---:|---|
| Heartbeat International | 47 | Promotes the 'abortion pill reversal' (APR) protocol as effective. Refuted as not evidence-based by ACOG and the FDA. |
| Ethics & Public Policy Center | 37 | Insurance-claims-database study claiming 10.93% of women experience serious adverse events from mifepristone — methodologically flawed; FDA's published rate is <0.5%. |
| CPCs and anti-abortion groups | 23 | Generic claims by crisis pregnancy centers and allied groups: services labeled 'medical care', anti-abortion advocacy framed as women's healthcare. |
| Project 2025 | 9 | Claims about Project 2025's abortion-related provisions; varies by article. |
| Robert F. Kennedy Jr. | 1 | Single mifepristone-related claim attributed to RFK Jr. |

## Top flagged articles (by similarity)

### [dailycaller.com] 1 In 10 Women Experience ‘Serious Adverse Event’ After Taking Abortion Pill, Study Says

- **URL**: https://dailycaller.com/2025/04/28/1-in-10-women-experience-serious-adverse-event-after-taking-abortion-pill-study-says/
- **Carries claim**: The EPPC report claims it’s the 'largest-known study of the abortion pill' and that nearly 11% of women 'experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [huffpost.com](https://www.huffpost.com/entry/gop-lays-groundwork-to-pull-abortion-pill-access-with-new-junk-science-report_n_6812975be4b04cfa6e2b45e0)
- **Evidence quote from article**: 'The study found that 10.93% of women experienced sepsis, infection, hemorrhaging, or another serious adverse event within 45 days after a mifepristone abortion.'
- **LLM reasoning**: The article presents the EPPC claim as factual, emphasizing its findings without mentioning the lack of peer-review, methodological transparency issues, or expert rebuttals that were previously used to debunk it.

### [foxnews.com] Experts sound the alarm over 'shocking' study showing significant risks to women who take abortion pills

- **URL**: https://www.foxnews.com/politics/experts-sound-alarm-over-shocking-study-showing-significant-risk-women-who-take-abortion-pills
- **Carries claim**: The EPPC report claims it’s the 'largest-known study of the abortion pill' and that nearly 11% of women 'experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [huffpost.com](https://www.huffpost.com/entry/gop-lays-groundwork-to-pull-abortion-pill-access-with-new-junk-science-report_n_6812975be4b04cfa6e2b45e0)
- **Evidence quote from article**: "After going through an abortion assisted by mifepristone, nearly 11% of women — more than one in 10 — reported experiencing 'infection, hemorrhaging, or another serious or life-threatening adverse event,' according to the study summary."
- **LLM reasoning**: The article presents the claim as factual, quoting the study's findings and pro-life advocates without mentioning the debunking or methodological flaws of the EPPC report.

### [ncregister.com] Study of Over 865,000 Abortion-Pill Patients: 11% Suffer ‘Serious Adverse Events’

- **URL**: https://www.ncregister.com/cna/eppc-study-on-abortion-pill-patients-11-suffer-serious-adverse-events
- **Carries claim**: The EPPC report claims it’s the 'largest-known study of the abortion pill' and that nearly 11% of women 'experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [huffpost.com](https://www.huffpost.com/entry/gop-lays-groundwork-to-pull-abortion-pill-access-with-new-junk-science-report_n_6812975be4b04cfa6e2b45e0)
- **Evidence quote from article**: 'A first-of-its-kind study by the Ethics and Public Policy Center that delves into public-health insurance records found that more than 1 in 10 women who take mifepristone to complete a chemical abortion will suffer a serious health complication during the process.'
- **LLM reasoning**: The article presents the EPPC study's claim uncritically, emphasizing its findings as factual and quoting proponents without addressing the debunking of the study's methodology or peer-review status.

### [ncregister.com] Government Will Conduct Abortion Pill Review Amid Studies Showing Possible Dangers

- **URL**: https://www.ncregister.com/cna/government-will-conduct-abortion-pill-review-amid-studies-showing-possible-dangers
- **Carries claim**: The EPPC report claims it’s the 'largest-known study of the abortion pill' and that nearly 11% of women 'experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [huffpost.com](https://www.huffpost.com/entry/gop-lays-groundwork-to-pull-abortion-pill-access-with-new-junk-science-report_n_6812975be4b04cfa6e2b45e0)
- **Evidence quote from article**: "The first-of-its-kind study, published by the Ethics and Public Policy Center on April 28, delved into public health insurance records, finding that about 11% of women suffer at least one 'serious adverse event' within 45 days of taking mifepristone for an abortion."
- **LLM reasoning**: The article presents the EPPC report's claim uncritically, quoting its findings without mentioning the lack of peer-review, methodological transparency, or expert rebuttals that previously debunked it.

### [ncregister.com] Sen. Hawley Urges FDA to Reinstate Abortion Drug Safety Regulations

- **URL**: https://www.ncregister.com/cna/sen-hawley-urges-fda-to-reinstate-abortion-drug-safety-regulations
- **Carries claim**: The EPPC report claims it’s the 'largest-known study of the abortion pill' and that nearly 11% of women 'experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [huffpost.com](https://www.huffpost.com/entry/gop-lays-groundwork-to-pull-abortion-pill-access-with-new-junk-science-report_n_6812975be4b04cfa6e2b45e0)
- **Evidence quote from article**: 'The study, released this week, found that more than 1 in 10 women who use mifepristone experience adverse side effects including sepsis, infection, hemorrhaging, or an emergency room visit.'
- **LLM reasoning**: The article presents the claim as factual without mentioning its debunking, framing it as evidence in Sen. Hawley’s argument to the FDA.

### [breitbart.com] Author of Shocking Abortion Pill Study Calls on FDA to Conduct Its Own Research

- **URL**: https://www.breitbart.com/health/2025/05/12/exclusive-author-shocking-abortion-pill-study-suggesting-higher-complication-rate-calls-on-trumps-fda-conduct-own-research/
- **Carries claim**: The EPPC report claims it’s the 'largest-known study of the abortion pill' and that nearly 11% of women 'experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [huffpost.com](https://www.huffpost.com/entry/gop-lays-groundwork-to-pull-abortion-pill-access-with-new-junk-science-report_n_6812975be4b04cfa6e2b45e0)
- **Evidence quote from article**: 'A study from the Ethics and Public Policy Center (EPPC) released at the end of April found that 10.93 percent of women who had mifepristone abortions [...] experienced severe complications including sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following the abortion.'
- **LLM reasoning**: The article presents the EPPC study's claim uncritically, quoting its findings and the author's assertions without mentioning the prior debunking or expert criticism.

### [redstate.com] If the Death Merchants Have Their way, Abortion Pill Reversal Will Become the Next Battleground

- **URL**: https://redstate.com/jenniferoo/2024/05/06/if-the-left-has-its-way-abortion-pill-reversal-will-become-the-next-battleground-n2173807
- **Carries claim**: The 'Abortion Pill Reversal' treatment can reverse medication abortions.
- **Originated by**: Heartbeat International
- **Debunked by**: [dailykos.com](https://www.dailykos.com/stories/2024/5/7/2239299/-New-York-sues-anti-abortion-groups-promoting-false-method-to-reverse-medication-abortion?pm_campaign=blog&pm_medium=rss&pm_source=)
- **Evidence quote from article**: 'Dr. Francis spoke with the Colson Center and told the host that APR has been shown to have a 70 percent success rate, with a documented 4,500 babies alive because of this intervention.'
- **LLM reasoning**: The article presents the claim as true, citing a 70% success rate and testimonials from medical professionals, while framing opposition to APR as an attempt to suppress pro-life advocacy.

### [dailysignal.com] The FDA’s Lethargy Is Harming Women and Overburdening Doctors

- **URL**: https://www.dailysignal.com/2026/02/04/the-fdas-lethargy-is-harming-women-and-overburdening-doctors/
- **Carries claim**: The Ethics and Public Policy Center report claims that mifepristone harms women, causing 1 in 10 patients to experience 'serious adverse events,' including hemorrhage, ER visits, ectopic pregnancy, and 'abortion-specific complications.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [cbsnews.com](https://www.cbsnews.com/texas/news/fda-review-mifepristone-abortion-pill-access/)
- **Evidence quote from article**: 'Wubbenhorst, who has treated the many serious physical and mental health effects of mifepristone, noted that the drug can cause infection, hemorrhage, the need for blood transfusions, and in extreme cases, death. Her testimony is buttressed by the FDA’s own data, which admits that about 1 out of 25 women who take mifepristone end up in the emergency room.'
- **LLM reasoning**: The article presents the claim uncritically, citing a physician’s testimony and FDA data to support the assertion that mifepristone causes serious adverse events, without addressing the debunking evidence or counterarguments.

### [breitbart.com] FDA Approves New Generic Version of Abortion Drug Mifepristone

- **URL**: https://www.breitbart.com/politics/2025/10/02/fda-approves-new-generic-version-of-abortion-drug-mifepristone-as-agency-continues-safety-review/
- **Carries claim**: The FDA never studied the safety of the two drugs (mifepristone and misoprostol) under the labeled conditions of use and ignored evidence that medication abortion causes more complications than surgical abortions.
- **Originated by**: CPCs and anti-abortion groups
- **Debunked by**: [alternet.org](https://www.alternet.org/the-abortion-pill-abortion-bans/)
- **Evidence quote from article**: 'A study from the Ethics and Public Policy Center (EPPC) found that 10.93 percent of women who had mifepristone abortions experienced severe complications... significantly higher than the less than 0.5 percent in clinical trials reported on the FDA-approved drug label.'
- **LLM reasoning**: The article presents the EPPC study's findings as evidence supporting the claim that medication abortion causes more complications than previously reported, aligning with the original debunked claim without refuting it.

### [breitbart.com] FDA Commissioner ‘Committed’ to Conducting Abortion Pill Review

- **URL**: https://www.breitbart.com/politics/2025/06/04/fda-commissioner-is-committed-to-conducting-a-review-of-abortion-pill-safety/
- **Carries claim**: The EPPC report claims it’s the 'largest-known study of the abortion pill' and that nearly 11% of women 'experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [huffpost.com](https://www.huffpost.com/entry/gop-lays-groundwork-to-pull-abortion-pill-access-with-new-junk-science-report_n_6812975be4b04cfa6e2b45e0)
- **Evidence quote from article**: 'The study from the Ethics and Public Policy Center (EPPC) found that 10.93 percent of women who had mifepristone abortions experienced severe complications including sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following the abortion.'
- **LLM reasoning**: The article repeats the EPPC claim uncritically, presenting its findings as a factual basis for the FDA review without mentioning the prior debunking or methodological criticisms.

### [breitbart.com] 22 GOP AG’s Ask RFK Jr., FDA to Reinstate Abortion Pill Safety Regulations

- **URL**: https://www.breitbart.com/health/2025/08/13/more-than-20-gop-ags-ask-rfk-jr-fda-reinstate-abortion-pill-safety-regulations/
- **Carries claim**: The FDA never studied the safety of the two drugs (mifepristone and misoprostol) under the labeled conditions of use and ignored evidence that medication abortion causes more complications than surgical abortions.
- **Originated by**: CPCs and anti-abortion groups
- **Debunked by**: [alternet.org](https://www.alternet.org/the-abortion-pill-abortion-bans/)
- **Evidence quote from article**: 'serious adverse events occur 22 times more often than stated on the drug’s label, while the drug is less than half as effective as claimed'
- **LLM reasoning**: The article presents the claim as a valid concern raised by the AGs and the EPPC study, quoting their findings without refuting them or contextualizing the debunked nature of the claim.

### [dailysignal.com] Report: Adverse Events Skyrocketed After Biden Loosened Abortion Guardrails

- **URL**: https://www.dailysignal.com/2026/03/10/women-deserve-better-adverse-events-skyrocketed-biden-removed-doctors-visit-requirement-on-abortion-pill-new-report-shows/
- **Carries claim**: The EPPC report claims it’s the 'largest-known study of the abortion pill' and that nearly 11% of women 'experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [huffpost.com](https://www.huffpost.com/entry/gop-lays-groundwork-to-pull-abortion-pill-access-with-new-junk-science-report_n_6812975be4b04cfa6e2b45e0)
- **Evidence quote from article**: 'A previous study from the Ethics and Public Policy Center found that 11% of women experience adverse health effects, such as sepsis, infection, and hemorrhaging, within 45 days of a chemical abortion.'
- **LLM reasoning**: The article repeats the EPPC's claim about the 11% adverse event rate without mentioning the prior debunking or citing counter-evidence, presenting it as a factual finding from a study.

### [dailysignal.com] EXCLUSIVE: Lawmaker Aims to Give Babies Faced With Being Aborted a ‘Second Chance at Life’

- **URL**: https://www.dailysignal.com/2025/09/17/exclusive-lawmaker-aims-to-give-babies-faced-with-being-aborted-second-chance-life/
- **Carries claim**: The 'Abortion Pill Reversal' treatment can reverse medication abortions.
- **Originated by**: Heartbeat International
- **Debunked by**: [dailykos.com](https://www.dailykos.com/stories/2024/5/7/2239299/-New-York-sues-anti-abortion-groups-promoting-false-method-to-reverse-medication-abortion?pm_campaign=blog&pm_medium=rss&pm_source=)
- **Evidence quote from article**: 'a treatment exists to reverse the effects of the abortion pill. Abortion pill reversal uses progesterone to reverse the effects of mifepristone to save the life of the unborn child.'
- **LLM reasoning**: The article presents the claim as a factual treatment option without refuting it, using descriptive language that implies its validity and quoting supporters who assert its potential efficacy.

### [dailysignal.com] 'A Decision You Can't Take Back': Mother Warns Against Colorado Law Prohibiting Abortion Pill Reversal After It Saved Daughter's Life

- **URL**: https://www.dailysignal.com/2024/10/01/decision-cant-take-mother-warns-colorado-law-prohibiting-abortion-pill-reversal-after-saved-daughters-life/
- **Carries claim**: The 'Abortion Pill Reversal' treatment can reverse medication abortions.
- **Originated by**: Heartbeat International
- **Debunked by**: [dailykos.com](https://www.dailykos.com/stories/2024/5/7/2239299/-New-York-sues-anti-abortion-groups-promoting-false-method-to-reverse-medication-abortion?pm_campaign=blog&pm_medium=rss&pm_source=)
- **Evidence quote from article**: 'Chelsea herself has proven that it definitely increases the chances that moms like Mackenna can save their babies.'
- **LLM reasoning**: The article presents the claim as true by quoting advocates who assert its effectiveness and frames the treatment as a viable option, despite legal challenges, without addressing the debunked scientific concerns.

### [foxnews.com] Hawley launches investigation into abortion drug manufacturers over 'grave risks' to women

- **URL**: https://www.foxnews.com/politics/hawley-launches-investigation-abortion-drug-manufacturers-over-grave-risks-women
- **Carries claim**: The Ethics and Public Policy Center report claims that mifepristone harms women, causing 1 in 10 patients to experience 'serious adverse events,' including hemorrhage, ER visits, ectopic pregnancy, and 'abortion-specific complications.'
- **Originated by**: Ethics & Public Policy Center
- **Debunked by**: [cbsnews.com](https://www.cbsnews.com/texas/news/fda-review-mifepristone-abortion-pill-access/)
- **Evidence quote from article**: "Research by the Ethics and Public Policy Center (EPPC) in Washington, D.C., showed the rate of side effects when using mifepristone is 22 times higher than indications from the FDA-approved drug label. The study revealed more than one in 10 women have reported experiencing 'infection, hemorrhaging, or another serious or life-threatening adverse event.'"
- **LLM reasoning**: The article repeats the EPPC's claim about mifepristone's adverse events without mentioning the prior debunking or presenting counter-evidence, effectively endorsing the claim as part of the context for the investigation.

## Output files for review

- `misinfo_carriers.csv` — every (article, claim) carrier verdict, one row per pair (117 rows)
- `misinfo_carriers_by_article.csv` — one row per unique flagged article (65 rows), with all claims it carries collected in `claims_carried_json`
- `stage4b_verdicts.json` — full LLM verdicts for all 2,177 candidate pairs (carrying + debunking + neutral_reporting + irrelevant)
- `claims_verified.json` — the canonical claim database used for retrieval
- `claims_all_with_ideology.json` — full annotated claim set with outlet ideology tags
- `articles_classified.csv` — Stage 1 article-type labels for the full eligible corpus

## Honest limits

- **Recall is bounded by the fact-check corpus.** We can only flag carriers of claims that some fact-checker in our corpus has already debunked. Novel misinfo not present in the fact-check set is invisible to this pipeline.
- **Two campaigns dominate**: Heartbeat International's APR (47/117) and EPPC's mifepristone study (37/117). The pipeline detects concentrated amplification, not diverse misinformation.
- **No Right-leaning fact-checkers in the corpus.** All Stage 3 'multi-ideology' verifications span Left/Center/Center-Left only. We're detecting consensus among media critics of these sources, not bipartisan agreement on what constitutes misinfo.
- **Verifier is qwen3:14b at temperature 0.** Sample validation found 8/8 correct labels in initial review, but the model can hallucinate evidence quotes — reviewers should always check the quote against the article text before publication.
- **9 candidate pairs (~0.4%) returned UNKNOWN** even after the recovery pass. They're recorded in `stage4b_verdicts.json` if you want to inspect manually.

## Reviewer workflow

Recommended: open `misinfo_carriers_by_article.csv` in Excel/sheets. For each row, click `article_url`, read the article, and verify the LLM's `evidence_quote` and `reasoning` fields actually match what the article says. Articles where the evidence quote is faithful and the framing genuinely uncritical can be promoted to the team's review pipeline.
