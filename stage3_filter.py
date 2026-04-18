"""Stage 3 of the cross-reference misinfo pipeline.

Take the raw claims from Stage 2 (`claims.json`), normalize claim-source names
(fuzzy match), tag each fact-check outlet with an ideology bucket, and promote
claims to the canonical database only if they're debunked by outlets from ≥2
different ideology buckets. This filters out one-side-attacking-the-other
editorial assertions.

Outputs:
- claims_verified.json: only claims with multi-ideology corroboration
- claims_all_with_ideology.json: full set with ideology annotations
"""
import json
from collections import defaultdict
from urllib.parse import urlparse

from rapidfuzz import fuzz, process

from source_ideology_tagger import IDEOLOGY_MAP

INPUT_JSON = "claims.json"
OUT_VERIFIED = "claims_verified.json"
OUT_ALL = "claims_all_with_ideology.json"

FUZZY_THRESHOLD = 85  # token_set_ratio; 100 = identical, 85 = close match

# Outlets whose solo fact-checking is treated as authoritative (bypasses the
# multi-ideology rule). Based on institutional reputation for rigorous
# fact-checking. Expand with care — adding an outlet here shortcuts the
# ideology cross-check.
AUTHORITATIVE_SOLO = {
    "factcheck.org", "scientificamerican.com", "npr.org", "cbsnews.com",
    "theguardian.com", "wired.com", "usatoday.com", "latimes.com",
}


def normalize_domain(media_name: str) -> str:
    if not media_name:
        return ""
    media_name = media_name.strip().lower()
    parsed = urlparse(media_name if media_name.startswith("http") else f"https://{media_name}")
    return parsed.netloc.replace("www.", "")


def tag_outlet(outlet: str) -> str:
    return IDEOLOGY_MAP.get(normalize_domain(outlet), "Unknown")


def normalize_source_names(raw_names):
    """Cluster similar claim-source strings and return {raw: canonical}."""
    uniq = sorted({n.strip() for n in raw_names if n and n.strip().lower() not in ("null", "none", "")})
    canonical = {}
    clusters = []  # list of (canonical, [aliases])
    for name in uniq:
        if not clusters:
            clusters.append((name, [name]))
            canonical[name] = name
            continue
        match = process.extractOne(
            name,
            [c[0] for c in clusters],
            scorer=fuzz.token_set_ratio,
            score_cutoff=FUZZY_THRESHOLD,
        )
        if match:
            matched_canonical = match[0]
            for i, (can, aliases) in enumerate(clusters):
                if can == matched_canonical:
                    # Prefer the shorter/cleaner canonical form
                    new_can = min([can, name], key=len) if len(name) < len(can) else can
                    clusters[i] = (new_can, aliases + [name])
                    for a in clusters[i][1]:
                        canonical[a] = new_can
                    break
        else:
            clusters.append((name, [name]))
            canonical[name] = name
    return canonical


def run():
    with open(INPUT_JSON) as f:
        articles = json.load(f)

    # Collect raw claim sources
    raw_sources = []
    for a in articles:
        for c in a["claims"]:
            s = (c.get("claim_source") or "").strip()
            if s and s.lower() not in ("null", "none", ""):
                raw_sources.append(s)

    name_map = normalize_source_names(raw_sources)
    dedup_count = len(raw_sources) - len(set(name_map.values()))
    print(f"[normalize] {len(raw_sources)} raw claim-source strings → {len(set(name_map.values()))} canonical (merged {dedup_count} duplicates)")

    # Annotate claims with canonical source + outlet ideology
    for a in articles:
        a["fact_check_outlet_ideology"] = tag_outlet(a["fact_check_outlet"])
        for c in a["claims"]:
            raw = (c.get("claim_source") or "").strip()
            c["claim_source_canonical"] = name_map.get(raw, raw) if raw else None

    with open(OUT_ALL, "w") as f:
        json.dump(articles, f, indent=2)
    print(f"[write] {OUT_ALL}")

    # Build source → set of (outlet, ideology) debunking it
    by_source = defaultdict(lambda: {"refutations": [], "ideologies": set(), "outlets": set()})
    for a in articles:
        outlet = a["fact_check_outlet"]
        ideology = a["fact_check_outlet_ideology"]
        for c in a["claims"]:
            canon = c.get("claim_source_canonical")
            if not canon:
                continue
            entry = by_source[canon]
            entry["outlets"].add(outlet)
            entry["ideologies"].add(ideology)
            entry["refutations"].append({
                "claim_text": c.get("claim_text"),
                "refutation": c.get("refutation"),
                "evidence_sources": c.get("evidence_sources", []),
                "fact_check_outlet": outlet,
                "fact_check_outlet_ideology": ideology,
                "fact_check_url": a["article_url"],
                "fact_check_title": a["article_title"],
                "topic": a["topic"],
            })

    # Stage 3 promotion rule: pass if EITHER
    #   (a) debunked by outlets from ≥2 distinct ideology buckets, OR
    #   (b) debunked by an AUTHORITATIVE_SOLO outlet (bypass for institutional
    #       fact-checkers whose solo verdict is taken as authoritative).
    verified = []
    rejected_summary = defaultdict(int)
    for source, entry in by_source.items():
        non_unknown = entry["ideologies"] - {"Unknown"}
        has_auth = any(
            normalize_domain(o) in AUTHORITATIVE_SOLO for o in entry["outlets"]
        )
        if len(non_unknown) >= 2 or has_auth:
            verified.append({
                "claim_source": source,
                "outlet_count": len(entry["outlets"]),
                "ideology_count": len(non_unknown),
                "ideologies": sorted(non_unknown),
                "outlets": sorted(entry["outlets"]),
                "verification_basis": (
                    "multi_ideology" if len(non_unknown) >= 2
                    else "authoritative_solo"
                ),
                "refutations": entry["refutations"],
            })
        else:
            reason = (
                "single_outlet" if len(entry["outlets"]) == 1
                else "single_ideology" if len(non_unknown) == 1
                else "all_unknown_ideology"
            )
            rejected_summary[reason] += 1

    verified.sort(key=lambda x: (x["verification_basis"] == "authoritative_solo",
                                  -x["ideology_count"], -x["outlet_count"]))

    with open(OUT_VERIFIED, "w") as f:
        json.dump(verified, f, indent=2)
    print(f"[write] {OUT_VERIFIED}")

    # Report
    total_sources = len(by_source)
    print()
    print("=" * 60)
    print(f"Stage 3 results")
    print("=" * 60)
    print(f"Total unique claim-sources:          {total_sources}")
    print(f"Verified (≥2 ideology buckets):      {len(verified)}")
    for reason, n in rejected_summary.items():
        print(f"  rejected: {reason:25s}    {n}")
    print()
    print("Top verified sources:")
    for v in verified[:15]:
        print(f"  {v['ideology_count']} ideologies × {v['outlet_count']} outlets | {v['claim_source'][:60]}")
        print(f"    ideologies: {', '.join(v['ideologies'])}")
        print(f"    outlets:    {', '.join(v['outlets'][:5])}")

    # Unknowns worth fixing
    unknown_outlets = {a["fact_check_outlet"] for a in articles
                       if a["fact_check_outlet_ideology"] == "Unknown"}
    if unknown_outlets:
        print()
        print(f"⚠ {len(unknown_outlets)} fact-check outlets untagged (ideology=Unknown):")
        for o in sorted(unknown_outlets):
            print(f"  {o}")


if __name__ == "__main__":
    run()
