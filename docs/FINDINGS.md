# Misinformation Carrier Findings

Output of the cross-reference misinformation detection pipeline run against a women's-health news corpus.

## Summary

- **187 carrying verdicts** flagged across **135 unique articles**.
- Each flagged article presents a previously-debunked claim as fact, without acknowledging the debunking.
- Every flag carries provenance: the originating actor, the fact-check that debunked it, the specific passage in the article, and the LLM's reasoning.

## Methodology

1. **Corpus** — 3,064 articles from MediaCloud, scraped with `trafilatura`. 1,751 passed eligibility (word count AND (regex topic-context gate OR semantic similarity ≥ 0.70) AND canonical-after-syndication-dedupe).
2. **Stage 1 — article classification** (`qwen3:14b`): 1,576 ORIGINAL, 61 FACT_CHECK, 49 OTHER, 65 unclassified.
3. **Stage 2 — claim extraction** from the 91 FACT_CHECK articles: 300 debunked claims with named originators.
4. **Stage 3 — ideology cross-reference**: promoted 38 claim-source groups to canonical (multi-ideology debunks or authoritative-solo outlets).
5. **Stage 4a — embedding retrieval** with `nomic-embed-text`: 1,576 articles × 111 unique claim-texts, top-K candidates per article above cosine similarity 0.65.
6. **Stage 4b — LLM verification** (`gpt-oss-safeguard:latest`) at sim ≥ 0.68: 2,917 candidate pairs classified as `carrying`, `debunking`, `neutral_reporting`, or `irrelevant`.

**Posture**: temperature=0, allowed-abstention output, no LLM call without grounded prior fact-check evidence.

## Validation

The Stage 4b verifier (`gpt-oss-safeguard:latest`) was selected via a 5-model bake-off against a 100-row stratified gold set labeled by Claude Opus 4.7 acting as judge. The shipped model was validated on a 641-row gold set covering all 187 production carrier flags + 134 debunking + 120 neutral_reporting (full population on three classes) + 200 irrelevant (cloud-judged):

| Metric | Value | Note |
|---|---|---|
| Carrier precision | **0.973** | 180/185 flags confirmed; 95% Wilson CI ~0.94–0.99 (near-population coverage) |
| Carrier recall | 0.692 | 180/260 sampled real carriers caught (stratification-biased on irrelevant) |
| Overall accuracy | 0.778 | 4-class agreement with cloud judge |

Operational meaning: **the carrier list above is approximately 182 real carriers + ~5 expected false positives** — high precision at the cost of missing roughly 30% of real carriers in the corpus. For a published list of named outlets this is the right bias: false positives damage credibility; missing some carriers is acceptable.

**Known failure mode**: 4/5 carrier false positives in v4 validation occurred on left-leaning outlets where the article was *about* a piece of misinformation (i.e., debunking it) and the verifier flagged the article as carrying the fact-checker's own statement. Pre-publication spot-check via `data/misinfo_carriers_spot_check.csv` is the right safeguard.

Full bake-off and gold-set methodology in `docs/BACKLOG.md` ('Stage 4b precision harness' and 'Stage 4b carrier-precision improvement attempts' sections).

## Carrier outlets

| Outlet | Carrier verdicts | Unique articles |
|---|---:|---:|
| lifesitenews.com | 65 | 40 |
| lifenews.com | 23 | 13 |
| dailysignal.com | 12 | 7 |
| ncregister.com | 9 | 7 |
| benzinga.com | 6 | 6 |
| foxnews.com | 6 | 3 |
| msmagazine.com | 4 | 4 |
| townhall.com | 3 | 3 |
| jezebel.com | 3 | 2 |
| vox.com | 2 | 2 |
| pjmedia.com | 2 | 2 |
| breitbart.com | 2 | 2 |
| bustle.com | 2 | 2 |
| slate.com | 2 | 2 |
| operationrescue.org | 2 | 2 |
| spectator.org | 2 | 2 |
| yahoo.com | 2 | 2 |
| talkingpointsmemo.com | 2 | 2 |
| huffpost.com | 2 | 2 |
| newstatesman.com | 2 | 1 |
| cnn.com | 2 | 1 |
| azcentral.com | 2 | 1 |
| motherjones.com | 2 | 1 |
| dailycaller.com | 2 | 1 |
| autostraddle.com | 2 | 1 |
| livescience.com | 1 | 1 |
| blackchronicle.com | 1 | 1 |
| hollywoodreporter.com | 1 | 1 |
| theconversation.com | 1 | 1 |
| jsonline.com | 1 | 1 |
| npr.org | 1 | 1 |
| usatoday.com | 1 | 1 |
| realclearpolitics.com | 1 | 1 |
| nationalmemo.com | 1 | 1 |
| businessinsider.com | 1 | 1 |
| nypost.com | 1 | 1 |
| vice.com | 1 | 1 |
| blackdoctor.org | 1 | 1 |
| theweek.com | 1 | 1 |
| newsbusters.org | 1 | 1 |
| thenation.com | 1 | 1 |
| mediamatters.org | 1 | 1 |
| secularprolife.org | 1 | 1 |
| buzzfeed.com | 1 | 1 |
| newsone.com | 1 | 1 |
| dailykos.com | 1 | 1 |
| salon.com | 1 | 1 |
| madamenoire.com | 1 | 1 |
| theguardian.com | 1 | 1 |

## Campaigns being amplified

| Originating actor | Carrier verdicts | Description |
|---|---:|---|
| Heartbeat International and other anti-abortion organizations | 27 | Abortion pill reversal can help women halt medical abortions. |
| Ethics and Public Policy Center (EPPC) | 26 | The EPPC report provides objective safety data showing that medication abortion is unsafe. |
| Heartbeat International and other anti-abortion activists | 25 | Abortion pill reversal can be used to reverse a medication abortion by taking large amounts of progesterone and not taking the misoprostol pills. |
| (unknown); Brett Kavanaugh; Jacob Rees-Mogg; Judge Brett Kavanaugh; Kanye West; Pill Club's survey respondents (men in the U.S.); Priests for Life; U.S. government (via USAID); null | 12 | Emergency contraception such as Plan B is an abortifacient and can induce abortion. |
| Jane’s Army | 10 | The anti-choice movement opposes reproductive health care and seeks to ban birth control and abortion. |
| Abortion Pill Reversal and other anti-choice organizations; Anti-abortion advocates and organizations such as Abortion Pill Reversal; Anti-abortion groups and state legislatures; George Delgado (pro-l | 8 | Progesterone can be used to reverse the effects of the abortion pill (mifepristone). |
| Ethics and Public Policy Center | 7 | The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.' |
| Goop | 7 | A supplement for menopausal women is formulated with botanicals that support hormonal balance. |
| Alternatives Pregnancy Center; Anti-choice advocates and crisis pregnancy centers; George Delgado; George Delgado and co-authors; Heartbeat International; Heartbeat International and 11 crisis pregnan | 6 | The 'abortion pill reversal' procedure is safe and effective. |
| Heartbeat International and other CPCs | 6 | Crisis pregnancy centers (CPCs) provide accurate and unbiased information about reproductive health care. |
| (unknown); A 2020 open letter from a coalition of pro-life groups; April analysis from EPPC; Charlotte Lozier Institute study; EPPC report; Ethics & Public Policy Center (EPPC); November 2021 study by | 5 | Serious adverse events from medication abortion are common. |
| Ms. Magazine | 5 | IUD insertion can be painful, but pain management options are available. |
| ILIA CALDERÓN, UNIVISION ANCHOR | 4 | The Supreme Court ruled that faith-based pregnancy centers are not compelled to inform women about family planning services, including abortion. |
| Planned Parenthood | 4 | The abortion drug mifepristone is 'safer than many other medicines like penicillin, Tylenol, and Viagra'. |
| Foundation Consumer Healthcare and Planned Parenthood | 4 | Emergency contraception like Plan B is not an abortion pill and does not harm an existing pregnancy. |
| SBA Pro-Life | 3 | This tragedy began with abortion drugs. |
| Elon Musk; Influencers on TikTok; Students for Life; Wellness influencers on TikTok | 3 | Hormonal birth control causes a wide range of serious health issues, including infertility, depression, acne, weight gain, and decreased libido. |
| Pro-abortion activists and their media proxies such as NPR, Reuters, the New Yor | 3 | Unrestricted abortion access is necessary for providing life-saving care for pregnant women. |
| Influencers; Ms. Magazine; Natural Cycles; Self-described 'hormone experts' on TikTok; TikToker | 3 | Fertility awareness methods are as effective as or more effective than hormonal birth control. |
| Ethics & Public Policy Center | 2 | One in 10 women experience a serious adverse event when using mifepristone to end a pregnancy. |
| Carrie N. Baker | 2 | The two medications used for abortion—mifepristone and misoprostol—are 97.4 percent effective and safer than Tylenol |
| Media and some doctors | 2 | Pro-life laws prevent physicians from treating ectopic pregnancies, miscarriages, or women suffering life-threatening complications, including complications from abortion. |
| Pro-abortion groups | 2 | Chemical abortion drugs are a 'safe and convenient' option for women. |
| American College of Obstetricians and Gynecologists (ACOG) | 2 | Claims regarding abortion 'reversal' treatment are not based on science and do not meet clinical standards. |
| Colorado Gov. Jared Polis | 2 | Project 2025 'puts limits on contraception' and 'threatens access to IVF.' |
| Letitia James, New York Attorney General | 1 | There is 'no credible evidence' to prove that abortion-pill reversal is either safe or effective. |
| Liberty Counsel Action | 1 | Chemical abortion drugs and human remains are contaminating waterways due to improper disposal by women. |
| SATCHA PRETTO, UNIVISION ANCHOR | 1 | The Supreme Court ruled against a California law that ordered health centers to inform patients about pathways to access low-cost or free procedures for birth control or for the termination of a pregnancy. |
| Media outlets, medical associations, and politicians | 1 | Abortion restrictions would make receiving medical care for ectopic pregnancies and miscarriages illegal, and people will die. |
| Danco Laboratories | 1 | Mifepristone abortion is safe and effective. |
| U.S. Agency for International Development (USAID) | 1 | The contraceptives destroyed by the Trump administration 'induced abortion.' |
| Alice Huling, Campaign for Accountability | 1 | Google allows crisis pregnancy centers to spread misleading information about contraception. |

## Top flagged articles (by similarity)

### [newstatesman.com] Why so many American women are ordering abortion pills online

- **URL**: https://www.newstatesman.com/world/north-america/2019/05/why-so-many-american-women-are-ordering-abortion-pills-online
- **Carries claim**: The abortion drug mifepristone is 'safer than many other medicines like penicillin, Tylenol, and Viagra'.
- **Originated by**: Planned Parenthood
- **Debunked by**: breitbart.com
- **Evidence quote from article**: 'Overall, the risk of complications is extremely low: according to the US FDA only 2 in every thousand women experience an adverse reaction to mifepristone – making it significantly safer than other widely-used drugs, such as Tylenol (known as Ibuprofen in the UK) or Viagra.'
- **LLM reasoning**: The article presents the claim that mifepristone is safer than Tylenol and Viagra as a factual statement without providing any counter‑evidence or refutation.

### [cnn.com] What is mifepristone?

- **URL**: https://www.cnn.com/mifepristone-abortion-pill-explained
- **Carries claim**: The abortion drug mifepristone is 'safer than many other medicines like penicillin, Tylenol, and Viagra'.
- **Originated by**: Planned Parenthood
- **Debunked by**: breitbart.com
- **Evidence quote from article**: 'Data analyzed by CNN shows that mifepristone is even safer than some of the most common prescription medications. The risk of death from penicillin, an antibiotic used to treat bacterial infections like pneumonia, for example, is four times greater than it is for mifepristone. The risk of death after taking Viagra – used to treat erectile dysfunction – is nearly 10 times higher.'
- **LLM reasoning**: The article repeats the safety comparison claim uncritically, presenting it as fact with supporting data.

### [benzinga.com] Menosoothe Under Review: Youth Hormone Supplement for Women with Exotic Breakfast Drink for Menopausal Relief

- **URL**: https://www.benzinga.com/pressreleases/25/04/g44991251/menosoothe-under-review-youth-hormone-supplement-for-women-with-exotic-breakfast-drink-for-menopau
- **Carries claim**: A supplement for menopausal women is formulated with botanicals that support hormonal balance.
- **Originated by**: Goop
- **Debunked by**: businessinsider.com
- **LLM reasoning**: The article presents the claim that the supplement is formulated with botanicals to support hormonal balance as a factual, promotional statement without any counter‑evidence or skepticism.

### [benzinga.com] Best Supplements for Menopause Ranked: WellMe MenoRescue for Women's Hormonal Health

- **URL**: https://www.benzinga.com/pressreleases/25/04/g44986686/best-supplements-for-menopause-ranked-wellme-menorescue-for-womens-hormonal-health
- **Carries claim**: A supplement for menopausal women is formulated with botanicals that support hormonal balance.
- **Originated by**: Goop
- **Debunked by**: businessinsider.com
- **LLM reasoning**: The article presents the claim that the supplement is formulated with botanicals to support hormonal balance as a factual endorsement of the product.

### [lifenews.com] Letitia James Just Lost a Huge Battle to Stop Pregnancy Centers from Saving Babies

- **URL**: https://www.lifenews.com/2025/12/03/letitia-james-just-lost-a-huge-battle-to-stop-pregnancy-centers-from-saving-babies/
- **Carries claim**: Abortion pill reversal can be used to reverse a medication abortion by taking large amounts of progesterone and not taking the misoprostol pills.
- **Originated by**: Heartbeat International and other anti-abortion activists
- **Debunked by**: jezebel.com
- **LLM reasoning**: The article presents the abortion‑pill reversal claim as a factual, effective procedure and praises it, without offering any counter‑evidence or skepticism.

### [lifesitenews.com] Abortion pill injuries are massively underreported due to activists, complicit media: new report

- **URL**: https://www.lifesitenews.com/news/abortion-pill-injuries-are-massively-underreported-due-to-activists-complicit-media-new-report/
- **Carries claim**: The Ethics and Public Policy Center report claims the pill harms women, causing 1 in 10 patients to experience what they call a 'serious adverse event,' including hemorrhage, ER visits, ectopic pregnancy and an undefined category of 'abortion-specific complications.'
- **Originated by**: Ethics and Public Policy Center
- **Debunked by**: cbsnews.com
- **Evidence quote from article**: '"10.93 percent of women experience sepsis, infection, hemorrhaging, or another serious adverse event within 45 days following a mifepristone abortion," the EPPC found in a report.'
- **LLM reasoning**: The article presents the EPPC claim as fact and uses it to support its narrative without offering any counter‑evidence or critique.

### [lifesitenews.com] Oklahoma legislature sends abortion pill reversal law to pro-life governor’s desk

- **URL**: https://www.lifesitenews.com/news/oklahoma-legislature-sends-abortion-pill-reversal-law-to-pro-life-governors-desk
- **Carries claim**: Abortion pill reversal can help women halt medical abortions.
- **Originated by**: Heartbeat International and other anti-abortion organizations
- **Debunked by**: cbsnews.com
- **LLM reasoning**: The article presents the reversal claim as factual and endorses it, without providing counter‑evidence or a neutral stance.

### [lifesitenews.com] Abortion pill reversal explains why life-saving technique isn’t ‘junk science’

- **URL**: https://www.lifesitenews.com/news/abortion-pill-reversal-explains-why-life-saving-technique-isnt-junk-science
- **Carries claim**: Abortion pill reversal can be used to reverse a medication abortion by taking large amounts of progesterone and not taking the misoprostol pills.
- **Originated by**: Heartbeat International and other anti-abortion activists
- **Debunked by**: jezebel.com
- **Evidence quote from article**: 'Abortion pill reversal consists of administering extra progesterone to counteract mifepristone’s effects, ideally within 24 hours of taking the abortion pill.'
- **LLM reasoning**: The article presents the reversal technique as a valid, evidence‑based method and endorses it, effectively repeating the claim uncritically.

### [ncregister.com] Pro-Abortion Group’s Study Finds Ingredient in Morning-After Pill Can Induce Abortion

- **URL**: https://www.ncregister.com/cna/morning-after-pill-can-induce-abortion
- **Carries claim**: Emergency contraception such as Plan B is an abortifacient and can induce abortion.
- **Originated by**: (unknown); Brett Kavanaugh; Jacob Rees-Mogg; Judge Brett Kavanaugh; Kanye West; Pill Club's survey respondents (men in the U.S.); Priests for Life; U.S. government (via USAID); null
- **Debunked by**: businessinsider.com, elitedaily.com, ibtimes.com, msmagazine.com, vice.com, yahoo.com
- **LLM reasoning**: The article presents the claim that emergency contraception can act as an abortifacient, citing a study and expert statements that support this view, thereby endorsing the claim rather than refuting it.

### [livescience.com] Is getting an IUD painful?

- **URL**: https://www.livescience.com/health/fertility-pregnancy-birth/is-getting-an-iud-painful
- **Carries claim**: IUD insertion can be painful, but pain management options are available.
- **Originated by**: Ms. Magazine
- **Debunked by**: all.org
- **LLM reasoning**: The article confirms that IUD insertion can be painful and lists various pain‑management methods, thereby presenting the claim as true.

### [benzinga.com] Her Bodhi Reviews – Best Natural Primal Queen Alternative for Hormonal Balance Weight Loss

- **URL**: https://www.benzinga.com/pressreleases/25/08/g47379946/her-bodhi-reviews-best-natural-primal-queen-alternative-for-hormonal-balance-weight-loss
- **Carries claim**: A supplement for menopausal women is formulated with botanicals that support hormonal balance.
- **Originated by**: Goop
- **Debunked by**: businessinsider.com
- **Evidence quote from article**: 'Each ingredient—whether Ashwagandha for stress relief, DIM for estrogen metabolism, or probiotics for gut balance—is carefully chosen, clinically studied, and disclosed in full.'
- **LLM reasoning**: The article presents the claim that HerBodhi is formulated with botanicals that support hormonal balance as a factual statement, without citing evidence or acknowledging any debunking, thereby endorsing the claim.

### [lifenews.com] She Reversed the Abortion Pill and Saved Her Baby's Life

- **URL**: https://www.lifenews.com/2026/04/03/she-reversed-the-abortion-pill-and-saved-her-babys-life/
- **Carries claim**: Abortion pill reversal can be used to reverse a medication abortion by taking large amounts of progesterone and not taking the misoprostol pills.
- **Originated by**: Heartbeat International and other anti-abortion activists
- **Debunked by**: jezebel.com
- **Evidence quote from article**: 'Abortion pill reversal is simply a dose of progesterone, which counteracts mifepristone and protects the uterine lining.'
- **LLM reasoning**: The article repeats the claim uncritically, presenting it as a proven method and endorsing it through a personal success story.

### [foxnews.com] I chose abortion, then changed my mind — California wants that choice gone

- **URL**: https://www.foxnews.com/opinion/chose-abortion-changed-mind-california-wants-choice-gone
- **Carries claim**: Abortion pill reversal can help women halt medical abortions.
- **Originated by**: Heartbeat International and other anti-abortion organizations
- **Debunked by**: cbsnews.com
- **LLM reasoning**: The article presents the reversal claim as true and endorses it without providing any counter‑evidence or critique.

### [blackchronicle.com] Doctor: NC pregnancy centers a ‘go-to’ for women in crisis this Christmas season

- **URL**: https://blackchronicle.com/southeast/north-carolina/doctor-nc-pregnancy-centers-a-go-to-for-women-in-crisis-this-christmas-season/
- **Carries claim**: Crisis pregnancy centers (CPCs) provide accurate and unbiased information about reproductive health care.
- **Originated by**: Heartbeat International and other CPCs
- **Debunked by**: jezebel.com
- **Evidence quote from article**: 'Bane said that “women who face an unexpected pregnancy are in a true crisis, and pregnancy centers empower them with information and provide excellent healthcare as they consider their options.”'
- **LLM reasoning**: The article presents the pregnancy centers as a trusted source of information and care, endorsing their role without any critique or mention of bias.

### [lifesitenews.com] Federal judge rules Colorado can’t force Catholic pregnancy center to stop abortion pill reversal

- **URL**: https://www.lifesitenews.com/news/federal-judge-rules-colorado-cant-force-catholic-pregnancy-center-to-stop-abortion-pill-reversal/
- **Carries claim**: Abortion pill reversal can help women halt medical abortions.
- **Originated by**: Heartbeat International and other anti-abortion organizations
- **Debunked by**: cbsnews.com
- **Evidence quote from article**: '"Abortion pill reversal is a safe and often effective treatment for women who change their minds about chemical abortion and can reverse the effects of the first chemical abortion drug, saving the life of the unborn child,"'
- **LLM reasoning**: The article presents the claim as true and endorses it with pro‑life sources, without offering any counter‑evidence or refutation.

## Output files for review

- `data/misinfo_carriers.csv` — every (article, claim) carrier verdict, one row per pair (187 rows)
- `data/misinfo_carriers_by_article.csv` — one row per unique flagged article (135 rows), with all claims it carries collected in `claims_carried_json`
- `data/stage4b_verdicts.json` — full LLM verdicts for all 2,917 candidate pairs
- `data/claims_verified.json` — the canonical claim database used for retrieval
- `data/articles_classified.csv` — Stage 1 article-type labels for the full eligible corpus

## Honest limits

- **Recall is bounded by the fact-check corpus.** We can only flag carriers of claims that some fact-checker in our corpus has already debunked. Novel misinfo not present in the fact-check set is invisible to this pipeline.
- **Two campaigns dominate**: Heartbeat International and other anti-abortion organizations (27/187) and Ethics and Public Policy Center (EPPC) (26/187). The pipeline detects concentrated amplification, not diverse misinformation.
- **Verifier is `gpt-oss-safeguard:latest` at temperature 0.** Evidence quotes are validated as literal substrings of the article body (whitespace + smart-quote normalized) and nulled if the LLM hallucinates. Reviewers should still spot-check the quote against the article text before publishing the outlet name — at carrier precision 0.973, ~3% of flagged verdicts are expected false positives, with a known skew toward left-leaning outlets where the article is *about* misinformation rather than carrying it.
- **22 candidate pairs returned UNKNOWN** after Stage 4b. Inspect in `data/stage4b_verdicts.json` if needed.

## Reviewer workflow

Recommended: open `data/misinfo_carriers_by_article.csv` in Excel/sheets. For each row, click `article_url`, read the article, and verify the LLM's `evidence_quote` and `reasoning` fields actually match what the article says. Articles where the evidence quote is faithful and the framing genuinely uncritical can be promoted to the team's review pipeline.
