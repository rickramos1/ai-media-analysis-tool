"""Stage 5: build reviewer outputs from Stage 4b verdicts.

Reads `data/stage4b_verdicts.json` (and a few upstream artifacts for methodology
counts) and emits:

- `data/misinfo_carriers_by_article.csv` — one row per unique flagged article,
  with all carrier claims collected in `claims_carried_json`.
- `docs/FINDINGS.md` — human-readable report.

Run after `pipeline/stage4b_verify.py` completes.
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from stage4b_verify import STAGE4B_MODEL

csv.field_size_limit(2**30)

# Models used at each LLM stage. STAGE4B_MODEL is imported from stage4b_verify
# so the methodology section stays in sync with whatever's actually configured.
STAGE1_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")

DEFAULT_VERDICTS_JSON = "data/stage4b_verdicts.json"
DEFAULT_ARTICLES_CLASSIFIED = "data/articles_classified.csv"
DEFAULT_RAW_ARTICLES = "data/womens_health_articles.csv"
DEFAULT_CLAIMS = "data/claims.json"
DEFAULT_CLAIMS_VERIFIED = "data/claims_verified.json"
DEFAULT_CANDIDATES = "data/stage4a_candidates.json"
DEFAULT_CARRIERS_CSV = "data/misinfo_carriers.csv"
DEFAULT_OUT_CSV = "data/misinfo_carriers_by_article.csv"
DEFAULT_OUT_MD = "docs/FINDINGS.md"
DEFAULT_SPOT_CHECK_CSV = "data/misinfo_carriers_spot_check.csv"
DEFAULT_TOP_N = 15
STAGE4A_SIM_DEFAULT = float(os.environ.get("STAGE4A_SIM", "0.65"))
STAGE4B_SIM_DEFAULT = float(os.environ.get("STAGE4B_SIM", "0.68"))


def load_verdicts(path):
    with open(path) as f:
        return json.load(f)


def build_carriers_by_article(verdicts, out_csv):
    carriers = [v for v in verdicts if v.get("verdict") == "carrying"]
    by_url = defaultdict(list)
    for c in carriers:
        by_url[c["article_url"]].append(c)

    rows = []
    for url, items in by_url.items():
        items.sort(key=lambda x: x["similarity"], reverse=True)
        first = items[0]
        claims_json = [
            {
                "claim_text": i["claim_text"],
                "claim_source": i["claim_source"],
                "fact_check_outlet": i["fact_check_outlet"],
                "fact_check_url": i["fact_check_url"],
                "evidence_quote": i.get("evidence_quote"),
                "reasoning": i.get("reasoning", ""),
                "similarity": i["similarity"],
            }
            for i in items
        ]
        campaigns = sorted({i["claim_source"] for i in items if i.get("claim_source")})
        rows.append({
            "article_url": url,
            "article_title": first["article_title"],
            "article_outlet": first["article_outlet"],
            "article_topic": first["article_topic"],
            "n_claims_carried": len(items),
            "max_similarity": round(max(i["similarity"] for i in items), 3),
            "carrier_campaigns": "; ".join(campaigns),
            "claims_carried_json": json.dumps(claims_json, ensure_ascii=False),
        })
    rows.sort(key=lambda r: (r["max_similarity"], r["n_claims_carried"]), reverse=True)

    df = pd.DataFrame(rows, columns=[
        "article_url", "article_title", "article_outlet", "article_topic",
        "n_claims_carried", "max_similarity", "carrier_campaigns", "claims_carried_json",
    ])
    df.to_csv(out_csv, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
    return df


def row_count(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return max(sum(1 for _ in f) - 1, 0)


def classification_counts(path):
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    if "article_type" not in df.columns:
        return {}
    return dict(Counter(df["article_type"]))


def claim_extraction_stats(path):
    if not os.path.exists(path):
        return {"fact_check_articles": None, "total_claims": None}
    with open(path) as f:
        d = json.load(f)
    total = sum(len(a.get("claims", [])) for a in d)
    return {"fact_check_articles": len(d), "total_claims": total}


def verified_claim_groups(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return len(json.load(f))


def candidate_universe(path):
    if not os.path.exists(path):
        return {"articles": None, "claims": None}
    with open(path) as f:
        d = json.load(f)
    return {"articles": len(d.get("per_article", [])), "claims": len(d.get("claims", []))}


def campaign_descriptions(verdicts):
    """Pick the most-carried claim_text for each claim_source as the description."""
    per_actor = defaultdict(Counter)
    for v in verdicts:
        if v.get("verdict") != "carrying":
            continue
        src = v.get("claim_source")
        text = (v.get("claim_text") or "").strip()
        if src and text:
            per_actor[src][text] += 1
    return {src: counter.most_common(1)[0][0] for src, counter in per_actor.items()}


def outlet_table(carriers_df):
    per_outlet = defaultdict(lambda: {"verdicts": 0, "articles": set()})
    for _, r in carriers_df.iterrows():
        per_outlet[r["article_outlet"]]["verdicts"] += int(r["n_claims_carried"])
        per_outlet[r["article_outlet"]]["articles"].add(r["article_url"])
    rows = [
        (outlet, stats["verdicts"], len(stats["articles"]))
        for outlet, stats in per_outlet.items()
    ]
    rows.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return rows


def campaign_table(verdicts, descriptions):
    carriers = [v for v in verdicts if v.get("verdict") == "carrying"]
    per_actor = Counter(c["claim_source"] for c in carriers if c.get("claim_source"))
    rows = []
    for actor, n in per_actor.most_common():
        rows.append((actor, n, descriptions.get(actor, "")))
    return rows


def render_top_articles(carriers_df, top_n):
    """Pick the highest-similarity carrier verdict per article; render top_n."""
    lines = []
    for _, row in carriers_df.head(top_n).iterrows():
        claims = json.loads(row["claims_carried_json"])
        featured = claims[0]
        lines.append(f"### [{row['article_outlet']}] {row['article_title']}")
        lines.append("")
        lines.append(f"- **URL**: {row['article_url']}")
        lines.append(f"- **Carries claim**: {featured['claim_text']}")
        lines.append(f"- **Originated by**: {featured['claim_source']}")
        fc_outlet = featured["fact_check_outlet"]
        fc_url = featured.get("fact_check_url") or ""
        if fc_url:
            lines.append(f"- **Debunked by**: [{fc_outlet}]({fc_url})")
        else:
            lines.append(f"- **Debunked by**: {fc_outlet}")
        if featured.get("evidence_quote"):
            quote = featured["evidence_quote"].strip()
            lines.append(f"- **Evidence quote from article**: '{quote}'")
        if featured.get("reasoning"):
            lines.append(f"- **LLM reasoning**: {featured['reasoning']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_findings(
    carriers_df, verdicts, out_md, top_n,
    raw_articles, class_counts, claim_stats,
    verified_groups, cand, campaigns, outlets,
    sim4a, sim4b,
):
    total_carriers = sum(1 for v in verdicts if v.get("verdict") == "carrying")
    unique_articles = len(carriers_df)
    unknown = sum(1 for v in verdicts if v.get("verdict") == "UNKNOWN")
    total_pairs = len(verdicts)

    def fmt(n):
        return f"{n:,}" if isinstance(n, int) else "?"

    eligible_count = sum(class_counts.values()) if class_counts else None
    methodology_lines = [
        f"1. **Corpus** — {fmt(raw_articles) if raw_articles is not None else '?'} articles from MediaCloud, "
        f"scraped with `trafilatura`. {fmt(eligible_count) if eligible_count is not None else '?'} passed eligibility "
        "(word count AND (regex topic-context gate OR semantic similarity ≥ 0.70) AND canonical-after-syndication-dedupe).",
        f"2. **Stage 1 — article classification** (`{STAGE1_MODEL}`): "
        f"{fmt(class_counts.get('ORIGINAL', 0))} ORIGINAL, "
        f"{fmt(class_counts.get('FACT_CHECK', 0))} FACT_CHECK, "
        f"{fmt(class_counts.get('OTHER', 0))} OTHER, "
        f"{fmt(class_counts.get('UNCLASSIFIED', 0))} unclassified.",
        f"3. **Stage 2 — claim extraction** from the {fmt(claim_stats.get('fact_check_articles'))} FACT_CHECK articles: "
        f"{fmt(claim_stats.get('total_claims'))} debunked claims with named originators.",
        f"4. **Stage 3 — ideology cross-reference**: promoted {fmt(verified_groups)} claim-source groups to canonical "
        "(multi-ideology debunks or authoritative-solo outlets).",
        f"5. **Stage 4a — embedding retrieval** with `nomic-embed-text`: "
        f"{fmt(cand.get('articles'))} articles × {fmt(cand.get('claims'))} unique claim-texts, "
        f"top-K candidates per article above cosine similarity {sim4a}.",
        f"6. **Stage 4b — LLM verification** (`{STAGE4B_MODEL}`) at sim ≥ {sim4b}: "
        f"{fmt(total_pairs)} candidate pairs classified as `carrying`, `debunking`, `neutral_reporting`, or `irrelevant`.",
    ]

    dominance = ""
    if campaigns:
        top_two = campaigns[:2]
        dom_pct = [f"{actor} ({n}/{total_carriers})" for actor, n, _ in top_two]
        dominance = (
            f"- **Two campaigns dominate**: {' and '.join(dom_pct)}. "
            "The pipeline detects concentrated amplification, not diverse misinformation."
        )

    body = []
    body.append("# Misinformation Carrier Findings\n")
    body.append(
        "Output of the cross-reference misinformation detection pipeline run against a "
        "women's-health news corpus.\n"
    )
    body.append("## Summary\n")
    body.append(f"- **{total_carriers} carrying verdicts** flagged across **{unique_articles} unique articles**.")
    body.append("- Each flagged article presents a previously-debunked claim as fact, without acknowledging the debunking.")
    body.append("- Every flag carries provenance: the originating actor, the fact-check that debunked it, the specific passage in the article, and the LLM's reasoning.\n")

    body.append("## Methodology\n")
    body.extend(methodology_lines)
    body.append("")
    body.append("**Posture**: temperature=0, allowed-abstention output, no LLM call without grounded prior fact-check evidence.\n")

    body.append("## Validation\n")
    body.append(
        f"The Stage 4b verifier (`{STAGE4B_MODEL}`) was selected via a 5-model bake-off "
        "against a 100-row stratified gold set labeled by Claude Opus 4.7 acting as judge. "
        "The shipped model was then validated on a 377-row gold set covering all production "
        "carrier flags + 100 each of debunking/irrelevant + 87 neutral_reporting (cloud-judged):\n"
    )
    body.append("| Metric | Value | Note |")
    body.append("|---|---|---|")
    body.append("| Carrier precision | **0.978** | 88/90 flags confirmed; 95% Wilson CI ~0.92–0.997 (population-level) |")
    body.append("| Carrier recall | 0.599 | 88/147 sampled real carriers caught (stratified-sample-biased) |")
    body.append("| Overall accuracy | 0.751 | 4-class agreement with cloud judge |")
    body.append("")
    body.append(
        "Operational meaning: **the carrier list above is approximately 65 real carriers + "
        "~2 expected false positives** — high precision at the cost of missing roughly 40% of "
        "real carriers in the corpus. For a published list of named outlets this is the right "
        "bias: false positives damage credibility; missing some carriers is acceptable.\n"
    )
    body.append(
        "Full bake-off and gold-set methodology in `docs/BACKLOG.md` ('Stage 4b precision harness' "
        "and 'Stage 4b carrier-precision improvement attempts' sections).\n"
    )

    body.append("## Carrier outlets\n")
    body.append("| Outlet | Carrier verdicts | Unique articles |")
    body.append("|---|---:|---:|")
    for outlet, n_verdicts, n_articles in outlets:
        body.append(f"| {outlet} | {n_verdicts} | {n_articles} |")
    body.append("")

    body.append("## Campaigns being amplified\n")
    body.append("| Originating actor | Carrier verdicts | Description |")
    body.append("|---|---:|---|")
    for actor, n, description in campaigns:
        body.append(f"| {actor} | {n} | {description} |")
    body.append("")

    body.append(f"## Top flagged articles (by similarity)\n")
    body.append(render_top_articles(carriers_df, top_n))

    body.append("## Output files for review\n")
    body.append(f"- `{DEFAULT_CARRIERS_CSV}` — every (article, claim) carrier verdict, one row per pair ({total_carriers} rows)")
    body.append(f"- `{DEFAULT_OUT_CSV}` — one row per unique flagged article ({unique_articles} rows), with all claims it carries collected in `claims_carried_json`")
    body.append(f"- `{DEFAULT_VERDICTS_JSON}` — full LLM verdicts for all {fmt(total_pairs)} candidate pairs")
    body.append(f"- `{DEFAULT_CLAIMS_VERIFIED}` — the canonical claim database used for retrieval")
    body.append(f"- `{DEFAULT_ARTICLES_CLASSIFIED}` — Stage 1 article-type labels for the full eligible corpus\n")

    body.append("## Honest limits\n")
    body.append("- **Recall is bounded by the fact-check corpus.** We can only flag carriers of claims that some fact-checker in our corpus has already debunked. Novel misinfo not present in the fact-check set is invisible to this pipeline.")
    if dominance:
        body.append(dominance)
    body.append(f"- **Verifier is `{STAGE4B_MODEL}` at temperature 0.** Evidence quotes are validated as literal substrings of the article body (whitespace + smart-quote normalized) and nulled if the LLM hallucinates. Reviewers should still spot-check the quote against the article text before publishing the outlet name — at carrier precision 0.978, ~1–2 of every 90 flagged verdicts are expected false positives.")
    body.append(f"- **{unknown} candidate pairs returned UNKNOWN** after Stage 4b. Inspect in `{DEFAULT_VERDICTS_JSON}` if needed.\n")

    body.append("## Reviewer workflow\n")
    body.append(
        f"Recommended: open `{DEFAULT_OUT_CSV}` in Excel/sheets. For each row, click `article_url`, "
        "read the article, and verify the LLM's `evidence_quote` and `reasoning` fields actually match what the "
        "article says. Articles where the evidence quote is faithful and the framing genuinely uncritical can be "
        "promoted to the team's review pipeline.\n"
    )

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(body))


def write_spot_check_csv(verdicts, out_csv):
    """Write one-row-per-(article, claim) carrier verdict CSV with two blank
    columns at the front for human review (`spot_check_ok`, `notes`). Used to
    eyeball every flag before publishing the outlet list externally."""
    from urllib.parse import urlparse

    arts = pd.read_csv(DEFAULT_ARTICLES_CLASSIFIED, dtype=str,
                        keep_default_na=False, encoding="utf-8")
    publish_dates = {r["url"]: r.get("publish_date", "") for _, r in arts.iterrows()}

    def domain(url):
        try:
            host = urlparse(url).netloc.lower()
            return host[4:] if host.startswith("www.") else host
        except Exception:
            return ""

    carriers = [v for v in verdicts if v.get("verdict") == "carrying"]
    carriers.sort(key=lambda v: (domain(v["article_url"]), -float(v.get("similarity", 0) or 0)))

    fields = [
        "spot_check_ok", "notes",
        "article_publish_date", "article_outlet", "article_title", "article_url",
        "claim_text", "claim_source", "fact_check_outlet", "fact_check_url",
        "evidence_quote", "reasoning", "similarity",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for v in carriers:
            w.writerow({
                "spot_check_ok": "",
                "notes": "",
                "article_publish_date": publish_dates.get(v["article_url"], ""),
                "article_outlet": v.get("article_outlet", ""),
                "article_title": v.get("article_title", ""),
                "article_url": v.get("article_url", ""),
                "claim_text": v.get("claim_text", ""),
                "claim_source": v.get("claim_source", ""),
                "fact_check_outlet": v.get("fact_check_outlet", ""),
                "fact_check_url": v.get("fact_check_url", ""),
                "evidence_quote": v.get("evidence_quote") or "",
                "reasoning": v.get("reasoning", ""),
                "similarity": v.get("similarity", ""),
            })
    return len(carriers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", default=DEFAULT_VERDICTS_JSON)
    ap.add_argument("--out-csv", default=DEFAULT_OUT_CSV)
    ap.add_argument("--out-md", default=DEFAULT_OUT_MD)
    ap.add_argument("--spot-check-csv", default=DEFAULT_SPOT_CHECK_CSV)
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    ap.add_argument("--sim4a", type=float, default=STAGE4A_SIM_DEFAULT)
    ap.add_argument("--sim4b", type=float, default=STAGE4B_SIM_DEFAULT)
    args = ap.parse_args()

    verdicts = load_verdicts(args.verdicts)
    carriers_df = build_carriers_by_article(verdicts, args.out_csv)
    print(f"[write] {args.out_csv}: {len(carriers_df)} unique articles")

    n_spot = write_spot_check_csv(verdicts, args.spot_check_csv)
    print(f"[write] {args.spot_check_csv}: {n_spot} carrier verdicts (review file)")

    raw_count = row_count(DEFAULT_RAW_ARTICLES)
    class_counts = classification_counts(DEFAULT_ARTICLES_CLASSIFIED)
    claim_stats = claim_extraction_stats(DEFAULT_CLAIMS)
    verified_groups = verified_claim_groups(DEFAULT_CLAIMS_VERIFIED)
    cand = candidate_universe(DEFAULT_CANDIDATES)
    descriptions = campaign_descriptions(verdicts)
    campaigns = campaign_table(verdicts, descriptions)
    outlets = outlet_table(carriers_df)

    render_findings(
        carriers_df, verdicts, args.out_md, args.top_n,
        raw_count, class_counts, claim_stats,
        verified_groups, cand, campaigns, outlets,
        args.sim4a, args.sim4b,
    )
    print(f"[write] {args.out_md}")


if __name__ == "__main__":
    main()
