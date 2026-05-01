# Misinformation Carrier Findings

Output of the cross-reference misinformation detection pipeline run against a women's-health news corpus.

## Summary

- **90 carrying verdicts** flagged across **67 unique articles**.
- Each flagged article presents a previously-debunked claim as fact, without acknowledging the debunking.
- Every flag carries provenance: the originating actor, the fact-check that debunked it, the specific passage in the article, and the LLM's reasoning.

## Methodology

1. **Corpus** — 1,486 articles from MediaCloud, scraped with `trafilatura`. 988 passed eligibility (word count AND (regex topic-context gate OR semantic similarity ≥ 0.70) AND canonical-after-syndication-dedupe).
2. **Stage 1 — article classification** (`qwen3:14b`): 915 ORIGINAL, 45 FACT_CHECK, 17 OTHER, 11 unclassified.
3. **Stage 2 — claim extraction** from the 45 FACT_CHECK articles: 154 debunked claims with named originators.
4. **Stage 3 — ideology cross-reference**: promoted 16 claim-source groups to canonical (multi-ideology debunks or authoritative-solo outlets).
5. **Stage 4a — embedding retrieval** with `nomic-embed-text`: 915 articles × 74 unique claim-texts, top-K candidates per article above cosine similarity 0.65.
6. **Stage 4b — LLM verification** (`qwen3:14b`) at sim ≥ 0.68: 1,763 candidate pairs classified as `carrying`, `debunking`, `neutral_reporting`, or `irrelevant`.

**Posture**: temperature=0, allowed-abstention output, no LLM call without grounded prior fact-check evidence.

## Carrier outlets

| Outlet | Carrier verdicts | Unique articles |
|---|---:|---:|
| ncregister.com | 17 | 11 |
| dailysignal.com | 13 | 9 |
| townhall.com | 9 | 8 |
| breitbart.com | 5 | 5 |
| pjmedia.com | 5 | 3 |
| foxnews.com | 5 | 3 |
| slate.com | 4 | 3 |
| redstate.com | 4 | 3 |
| dailycaller.com | 4 | 3 |
| spectator.org | 4 | 3 |
| nypost.com | 4 | 2 |
| jezebel.com | 3 | 3 |
| latimes.com | 2 | 1 |
| dailykos.com | 2 | 1 |
| theconversation.com | 1 | 1 |
| thenation.com | 1 | 1 |
| motherjones.com | 1 | 1 |
| rawstory.com | 1 | 1 |
| gazettenet.com | 1 | 1 |
| vox.com | 1 | 1 |
| upi.com | 1 | 1 |
| huffpost.com | 1 | 1 |
| oregonlive.com | 1 | 1 |

## Campaigns being amplified

| Originating actor | Carrier verdicts | Description |
|---|---:|---|
| Heartbeat International and other anti-abortion organizations | 18 | Abortion pill reversal can help women halt medical abortions. |
| Ethics and Public Policy Center | 17 | The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.' |
| Abortion Pill Reversal and other anti-choice organizations; Anti-abortion advocates and organizations such as Abortion Pill Reversal; Anti-choice advocates and crisis pregnancy centers; Heartbeat Inte | 8 | There is an antidote to the abortion pill — you can reverse it with progesterone. |
| Heartbeat International and other CPCs | 7 | Crisis pregnancy centers (CPCs) provide accurate and unbiased information about reproductive health care. |
| Abortion Pill Reversal and other anti-choice organizations; Heartbeat International and 11 crisis pregnancy centers affiliated with the nonp; Heartbeat International and other anti-abortion activists | 6 | Abortion pill reversal can be used to reverse a medication abortion by taking large amounts of progesterone and not taking the misoprostol pills. |
| Planned Parenthood | 6 | The abortion drug mifepristone is 'safer than many other medicines like penicillin, Tylenol, and Viagra.' |
| Ethics & Public Policy Center | 4 | One in 10 women experience a serious adverse event when using mifepristone to end a pregnancy. |
| Pro-abortion groups | 4 | Chemical abortion drugs are a 'safe and convenient' option for women. |
| Anti-choice advocates and crisis pregnancy centers; Heartbeat International; Heartbeat International and 11 crisis pregnancy centers affiliated with the nonp; Heartbeat International and anti-abortion | 3 | The 'abortion pill reversal' procedure is safe and effective. |
| Pro-abortion activists and their media proxies such as NPR, Reuters, the New Yor | 3 | Unrestricted abortion access is necessary for providing life-saving care for pregnant women. |
| Danco Laboratories | 2 | Mifepristone abortion is safe and effective. |
| Mylissa Farmer, as reported by The Springfield News-Leader | 2 | Mylissa Farmer was unable to receive an abortion in Missouri and had to travel out of state for the procedure. |
| American College of Obstetricians and Gynecologists (ACOG) | 1 | Claims regarding abortion 'reversal' treatment are not based on science and do not meet clinical standards. |
| ProPublica | 1 | ProPublica's story on Amber Thurman implies that doctors waited so long because of the state’s abortion laws. |
| Mike Johnson | 1 | The morning after pill, as we know, is an abortifacient. |
| Students for Life | 1 | Hormonal birth control causes abortions and causes problems like infertility |
| Missouri Republican bill sponsor | 1 | Anything that destroys that life is abortion, it’s not birth control. |
| Media and some doctors | 1 | Pro-life laws prevent physicians from treating ectopic pregnancies, miscarriages, or women suffering life-threatening complications, including complications from abortion. |
| (unknown) | 1 | Home remedies for abortion are safe. |
| Elon Musk | 1 | Hormonal birth control makes you fat, doubles risk of depression & triples risk of suicide |
| Influencers on social media | 1 | Hormonal contraception can be responsible for bad romantic decisions because you are 'attracted to different men than you would be if you were off the pill' |
| U.S. Agency for International Development (USAID) | 1 | The contraceptives destroyed by the Trump administration 'induced abortion.' |

## Top flagged articles (by similarity)

### [nypost.com] One in 10 chemical abortions end in serious health complications: report

- **URL**: https://nypost.com/2025/04/28/us-news/one-in-10-chemical-abortions-end-in-serious-health-complications-report/
- **Carries claim**: The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.'
- **Originated by**: Ethics and Public Policy Center
- **Debunked by**: cbsnews.com
- **Evidence quote from article**: 'Nearly 11% of women who have taken a chemical abortion pill in recent years have experienced a serious adverse health event — such as infection, hemorrhage or sepsis — according to a report from a conservative group that reviewed insurance claims data.'
- **LLM reasoning**: The article presents the 1‑in‑10 serious‑adverse‑event statistic as a factual finding from a report, without providing counter‑evidence or a balanced perspective.

### [breitbart.com] Shocking Data Suggests Abortion Pill Injuries 22 Times Higher Than Reported

- **URL**: https://www.breitbart.com/politics/2025/04/28/exclusive-shocking-data-suggests-abortion-pill-complications-22-times-higher-than-previously-reported-fda-must-reinstate-stronger-safeguards/
- **Carries claim**: The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.'
- **Originated by**: Ethics and Public Policy Center
- **Debunked by**: cbsnews.com
- **LLM reasoning**: The article repeats the Ethics and Public Policy Center’s claim that 1 in 10 women experience serious adverse events without providing counter‑evidence or a balanced perspective, presenting it as fact.

### [slate.com] If the “Abortion Pill” Gets Banned, There’s Still One Good Move

- **URL**: https://slate.com/news-and-politics/2023/02/abortion-pill-ban-texas-mifepristone-misoprostol.html?via=rss
- **Carries claim**: The abortion drug mifepristone is 'safer than many other medicines like penicillin, Tylenol, and Viagra.'
- **Originated by**: Planned Parenthood
- **Debunked by**: breitbart.com
- **Evidence quote from article**: 'decades of research and several million abortions with mifepristone—including more than 3.7 million in the U.S.—have shown the drug to be safer than Tylenol'
- **LLM reasoning**: The article repeats the safety claim about mifepristone being safer than Tylenol without refuting it, presenting it as a fact.

### [redstate.com] If the Death Merchants Have Their way, Abortion Pill Reversal Will Become the Next Battleground

- **URL**: https://redstate.com/jenniferoo/2024/05/06/if-the-left-has-its-way-abortion-pill-reversal-will-become-the-next-battleground-n2173807
- **Carries claim**: Abortion pill reversal can help women halt medical abortions.
- **Originated by**: Heartbeat International and other anti-abortion organizations
- **Debunked by**: cbsnews.com
- **Evidence quote from article**: 'Abortion Pill Reversal provides real hope for women who want to stop their abortions and continue their pregnancies.'
- **LLM reasoning**: The article repeats the claim that abortion pill reversal can halt medical abortions as fact, citing purported success rates and pro‑life doctors without presenting any counter‑evidence.

### [pjmedia.com] Liz Warren and Her Coven of Witches Don't Care About Women. Here's How We Know.

- **URL**: https://pjmedia.com/columns/paula-bolyard/2022/07/07/liz-warren-the-right-refuses-to-help-pregnant-people-also-liz-warren-shut-down-all-the-crisis-pregnancy-centers-n1611137
- **Carries claim**: Crisis pregnancy centers (CPCs) provide accurate and unbiased information about reproductive health care.
- **Originated by**: Heartbeat International and other CPCs
- **Debunked by**: jezebel.com
- **LLM reasoning**: The article presents crisis pregnancy centers as offering comprehensive, free services and proper prenatal care, implying they provide accurate and unbiased information, thereby endorsing the claim.

### [foxnews.com] Experts sound the alarm over 'shocking' study showing significant risks to women who take abortion pills

- **URL**: https://www.foxnews.com/politics/experts-sound-alarm-over-shocking-study-showing-significant-risk-women-who-take-abortion-pills
- **Carries claim**: The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.'
- **Originated by**: Ethics and Public Policy Center
- **Debunked by**: cbsnews.com
- **LLM reasoning**: The article repeats the Ethics & Public Policy Center’s claim about a 1‑in‑10 serious adverse event rate uncritically, presenting it as fact without counter‑evidence.

### [breitbart.com] HHS Secretary RFK Jr. Orders ‘Complete Review’ of Abortion Pill

- **URL**: https://www.breitbart.com/politics/2025/05/15/hhs-secretary-rfk-jr-orders-complete-review-of-abortion-pill-after-shocking-study/
- **Carries claim**: The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.'
- **Originated by**: Ethics and Public Policy Center
- **Debunked by**: cbsnews.com
- **LLM reasoning**: The article presents the EPPC claim as a factual finding and uses it to support a call for stricter safeguards, without refuting or questioning its validity.

### [foxnews.com] I chose abortion, then changed my mind — California wants that choice gone

- **URL**: https://www.foxnews.com/opinion/chose-abortion-changed-mind-california-wants-choice-gone
- **Carries claim**: Abortion pill reversal can help women halt medical abortions.
- **Originated by**: Heartbeat International and other anti-abortion organizations
- **Debunked by**: cbsnews.com
- **LLM reasoning**: The article presents the reversal claim as fact and endorses it without providing any counter‑evidence or critique.

### [dailysignal.com] EXCLUSIVE: Lawmaker Aims to Give Babies Faced With Being Aborted a ‘Second Chance at Life’

- **URL**: https://www.dailysignal.com/2025/09/17/exclusive-lawmaker-aims-to-give-babies-faced-with-being-aborted-second-chance-life/
- **Carries claim**: Abortion pill reversal can help women halt medical abortions.
- **Originated by**: Heartbeat International and other anti-abortion organizations
- **Debunked by**: cbsnews.com
- **Evidence quote from article**: 'If a woman takes mifepristone and then decides she does not want to continue with the abortion, a treatment exists to reverse the effects of the abortion pill. Abortion pill reversal uses progesterone to reverse the effects of mifepristone to save the life of the unborn child.'
- **LLM reasoning**: The article repeats the claim that abortion pill reversal can halt a medical abortion and presents it as a factual, viable option without any counter‑evidence or skepticism.

### [theconversation.com] Women in Ghana can access safe abortions: why are so many still using unsafe methods?

- **URL**: https://theconversation.com/women-in-ghana-can-access-safe-abortions-why-are-so-many-still-using-unsafe-methods-274991
- **Carries claim**: Mifepristone abortion is safe and effective.
- **Originated by**: Danco Laboratories
- **Debunked by**: patriotpost.us
- **Evidence quote from article**: 'When used correctly and with proper guidance it is an acceptable, effective and safe method.'
- **LLM reasoning**: The article presents the claim that mifepristone abortion is safe and effective as a factual statement, endorsing it while also noting conditions for safety.

### [thenation.com] The Supreme Court Sides With the FDA on the Abortion Pill—for Now

- **URL**: https://www.thenation.com/article/society/supreme-court-fda-mifepristone-abortion/
- **Carries claim**: The abortion drug mifepristone is 'safer than many other medicines like penicillin, Tylenol, and Viagra.'
- **Originated by**: Planned Parenthood
- **Debunked by**: breitbart.com
- **Evidence quote from article**: 'In reality, the drug was safe and would eventually be considered safer than penicillin and Viagra.'
- **LLM reasoning**: The article presents the claim that mifepristone is safer than penicillin and Viagra as a factual statement, endorsing it without refutation.

### [motherjones.com] On its 25th birthday, mifepristone is more under attack than ever

- **URL**: https://www.motherjones.com/politics/2025/09/on-its-25th-birthday-mifepristone-abortion-pill-is-more-under-attack-than-ever/
- **Carries claim**: The abortion drug mifepristone is 'safer than many other medicines like penicillin, Tylenol, and Viagra.'
- **Originated by**: Planned Parenthood
- **Debunked by**: breitbart.com
- **Evidence quote from article**: 'As Carrie N. Baker, a Smith College professor and author of Abortion Pills: US History and Politics, told my colleague Nina Martin earlier this year, medication abortion “really is safer than Tylenol.”'
- **LLM reasoning**: The article repeats the claim that mifepristone is safer than Tylenol (and by extension other medicines) without providing a counter‑argument, thereby presenting it uncritically as a fact.

### [dailysignal.com] Report: Adverse Events Skyrocketed After Biden Loosened Abortion Guardrails

- **URL**: https://www.dailysignal.com/2026/03/10/women-deserve-better-adverse-events-skyrocketed-biden-removed-doctors-visit-requirement-on-abortion-pill-new-report-shows/
- **Carries claim**: The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.'
- **Originated by**: Ethics and Public Policy Center
- **Debunked by**: cbsnews.com
- **Evidence quote from article**: 'The rate of serious adverse events was 10.15% when a requirement was in effect that women visit health clinics in person to obtain the pill. However, it jumped to 11.50% when that requirement was removed, according to the new report from the Ethics and Public Policy Center.'
- **LLM reasoning**: The article presents the EAPC’s claim about adverse events as fact without providing counter‑evidence or a balanced perspective.

### [latimes.com] Column: The abortion pill is safe. Is your uterus?

- **URL**: https://www.latimes.com/politics/story/2024-06-13/chabria-column-supreme-court-mifepristone-abortion-pill-ruling
- **Carries claim**: Mifepristone abortion is safe and effective.
- **Originated by**: Danco Laboratories
- **Debunked by**: patriotpost.us
- **LLM reasoning**: The column explicitly states and endorses the claim that mifepristone is safe, presenting it as fact without any counter‑evidence.

### [ncregister.com] Government Will Conduct Abortion Pill Review Amid Studies Showing Possible Dangers

- **URL**: https://www.ncregister.com/cna/government-will-conduct-abortion-pill-review-amid-studies-showing-possible-dangers
- **Carries claim**: The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.'
- **Originated by**: Ethics and Public Policy Center
- **Debunked by**: cbsnews.com
- **Evidence quote from article**: 'The first-of-its-kind study, published by the Ethics and Public Policy Center on April 28, delved into public health insurance records, finding that about 11% of women suffer at least one “serious adverse event” within 45 days of taking mifepristone for an abortion.'
- **LLM reasoning**: The article repeats the Ethics and Public Policy Center’s findings uncritically, using them to support the narrative that the abortion pill is dangerous, without providing any counter‑evidence or debunking.

## Output files for review

- `data/misinfo_carriers.csv` — every (article, claim) carrier verdict, one row per pair (90 rows)
- `data/misinfo_carriers_by_article.csv` — one row per unique flagged article (67 rows), with all claims it carries collected in `claims_carried_json`
- `data/stage4b_verdicts.json` — full LLM verdicts for all 1,763 candidate pairs
- `data/claims_verified.json` — the canonical claim database used for retrieval
- `data/articles_classified.csv` — Stage 1 article-type labels for the full eligible corpus

## Honest limits

- **Recall is bounded by the fact-check corpus.** We can only flag carriers of claims that some fact-checker in our corpus has already debunked. Novel misinfo not present in the fact-check set is invisible to this pipeline.
- **Two campaigns dominate**: Heartbeat International and other anti-abortion organizations (18/90) and Ethics and Public Policy Center (17/90). The pipeline detects concentrated amplification, not diverse misinformation.
- **Verifier is qwen3:14b at temperature 0.** The model can hallucinate evidence quotes — reviewers should always check the quote against the article text before publication.
- **6 candidate pairs returned UNKNOWN** after Stage 4b. Inspect in `data/stage4b_verdicts.json` if needed.

## Reviewer workflow

Recommended: open `data/misinfo_carriers_by_article.csv` in Excel/sheets. For each row, click `article_url`, read the article, and verify the LLM's `evidence_quote` and `reasoning` fields actually match what the article says. Articles where the evidence quote is faithful and the framing genuinely uncritical can be promoted to the team's review pipeline.
