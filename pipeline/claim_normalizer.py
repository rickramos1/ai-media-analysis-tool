"""Normalize specific debunked claim texts into canonical claim families.

Many debunked claims are restatements of the same underlying misinfo frame
(e.g., "Plan B causes abortions" ≈ "EC inhibits implantation" ≈ "IUDs are
abortifacients"). Stage 4a retrieves against these family-level canonicals
rather than literal quoted claims so it catches broader frames.

Design: chunked clustering with cross-batch fuzzy merge. The original
single-LLM-call design returned prose summaries instead of JSON above ~150
input claims (qwen3 num_ctx=8192 fragility). We now batch claims into
chunks of ~40, cluster each batch, and merge resulting families across
batches by fuzzy-matching the canonical_claim text.

Outputs:
- claim_families.json           — all families
- claim_families_filtered.json  — families whose canonical claim is women's-health-relevant
                                  (drops off-topic claims that got in via contaminated
                                  fact-check roundups — ADHD meds, COVID, Medicaid, etc.)
"""
import argparse
import json
import os
import re
import time
import urllib.request
from collections import defaultdict

from dotenv import load_dotenv
from rapidfuzz import fuzz, process

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")

INPUT_CLAIMS = "data/claims.json"
OUTPUT_FAMILIES = "data/claim_families.json"
OUTPUT_FILTERED = "data/claim_families_filtered.json"

DEFAULT_CHUNK_SIZE = 40
MERGE_FUZZ_THRESHOLD = 80  # rapidfuzz token_set_ratio; matches Stage 3's source-name threshold

# Women's-health vocabulary. Families whose canonical_claim matches this keep
# going to Stage 4a; others are off-topic contamination from broad fact-check
# articles (e.g., factcheck.org weekly roundups). Expand if needed.
WOMENS_HEALTH_RX = re.compile(
    r"\b(birth control|contracepti(on|ve|ves)|IUDs?|Plan B|morning[- ]after|"
    r"ulipristal|levonorgestrel|abortion|mifepristone|Mifeprex|RU[- ]?486|"
    r"misoprostol|pregnan[ct]|abortifacient|crisis pregnancy|CPC|hormonal|"
    r"menstrua|reproduc|OB[- ]?GYN|gynecolog|ovulat|fertility|menopause|"
    r"fallopian|cervical|uterine|ovari|women.s health|women'?s health|"
    r"fetus|embryo|implantation|chemical abortion|abortion pill)\b",
    re.IGNORECASE,
)

PROMPT = """/no_think
You are clustering debunked claims into canonical families. Two claims belong to the same family if they express the same underlying factual misconception, even if phrased differently or attributed to different sources.

Return ONLY a JSON object with this structure:
{{
  "families": [
    {{
      "id": 1,
      "canonical_claim": "one neutral sentence capturing the shared misinformation frame",
      "member_ids": [claim_id, claim_id, ...]
    }},
    ...
  ]
}}

Rules:
- Every input claim_id must belong to exactly one family.
- Canonical claims should be specific enough to be testable in an article (not "vaccines are dangerous" but "the HPV vaccine causes infertility").
- Use neutral phrasing. Do not label claims as "misleading" or "false" — just state the claim itself.
- Group claims that share the same underlying factual assertion, even if they attribute the claim to different people.
- Aim for 5–12 families given this batch size. Claims with unique content can be their own family.

CLAIMS TO CLUSTER:
{claims_block}
"""


FAMILY_SCHEMA = {
    "type": "object",
    "properties": {
        "families": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "canonical_claim": {"type": "string"},
                    "member_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["id", "canonical_claim", "member_ids"],
            },
        },
    },
    "required": ["families"],
}


def call_llm(prompt, num_predict=1500):
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        # Ollama's native reasoning toggle. The `/no_think` prompt directive is
        # silently ignored by qwen3:14b, which then burns the entire num_predict
        # budget on a <think> block and returns empty `response`. think=false
        # makes the model emit the answer directly.
        "think": False,
        # Schema-constrained generation (Ollama 0.5+). Token-level masking
        # guarantees the response parses as JSON matching FAMILY_SCHEMA, which
        # eliminates the prose-summary failure mode that previously affected
        # ~1 in 5 batches at chunk_size=40 even with think=false.
        "format": FAMILY_SCHEMA,
        "options": {"temperature": 0, "num_predict": num_predict, "num_ctx": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8")).get("response", "")


def extract_json(s):
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except json.JSONDecodeError:
        return None


def cluster_batch(batch_claims):
    """Cluster one batch of claims via the LLM. Returns list of
    {canonical_claim, member_ids} dicts (member_ids restricted to this batch).

    On parse failure: each claim becomes its own singleton family so nothing
    is lost — downstream merge handles dedupe.
    """
    expected_ids = {c["claim_id"] for c in batch_claims}
    lines = [
        f"  id={c['claim_id']} [topic={c['topic']}] [source={c['claim_source']}] {c['claim_text']}"
        for c in batch_claims
    ]
    prompt = PROMPT.format(claims_block="\n".join(lines))

    t0 = time.time()
    resp = call_llm(prompt)
    elapsed = time.time() - t0

    parsed = extract_json(resp)
    if not parsed or "families" not in parsed:
        print(f"  [batch] {elapsed:.1f}s — PARSE FAILED, falling back to singletons "
              f"({len(batch_claims)} claims)")
        return [{"canonical_claim": c["claim_text"], "member_ids": [c["claim_id"]]}
                for c in batch_claims]

    families = parsed["families"]
    # Restrict member_ids to expected set; collect any unassigned and add as singletons.
    cleaned = []
    seen_ids = set()
    for fam in families:
        canon = (fam.get("canonical_claim") or "").strip()
        if not canon:
            continue
        members = [mid for mid in (fam.get("member_ids") or []) if mid in expected_ids]
        if not members:
            continue
        cleaned.append({"canonical_claim": canon, "member_ids": members})
        seen_ids.update(members)

    missing = expected_ids - seen_ids
    if missing:
        for c in batch_claims:
            if c["claim_id"] in missing:
                cleaned.append({"canonical_claim": c["claim_text"], "member_ids": [c["claim_id"]]})
        print(f"  [batch] {elapsed:.1f}s — {len(cleaned)} families ({len(missing)} unassigned → singletons)")
    else:
        print(f"  [batch] {elapsed:.1f}s — {len(cleaned)} families covering all {len(expected_ids)} claims")

    return cleaned


def merge_families(batch_families):
    """Union families across batches by fuzzy-matching canonical_claim text.

    Two families merge if their canonical_claim has token_set_ratio ≥
    MERGE_FUZZ_THRESHOLD. On merge, member_ids are unioned and the shorter
    canonical text wins (favors crisper phrasing).
    """
    merged = []  # list of {canonical_claim, member_ids: set}
    for fam in batch_families:
        canon = fam["canonical_claim"]
        members = set(fam["member_ids"])
        if not merged:
            merged.append({"canonical_claim": canon, "member_ids": members})
            continue
        match = process.extractOne(
            canon,
            [m["canonical_claim"] for m in merged],
            scorer=fuzz.token_set_ratio,
            score_cutoff=MERGE_FUZZ_THRESHOLD,
        )
        if match:
            matched_canon = match[0]
            for m in merged:
                if m["canonical_claim"] == matched_canon:
                    m["member_ids"] |= members
                    if len(canon) < len(m["canonical_claim"]):
                        m["canonical_claim"] = canon
                    break
        else:
            merged.append({"canonical_claim": canon, "member_ids": members})
    return merged


def run(chunk_size=DEFAULT_CHUNK_SIZE):
    # Read the flat list of refutations from claims.json. Each refutation is
    # a distinct claim_text; assign a dense claim_id.
    with open(INPUT_CLAIMS) as f:
        raw = json.load(f)
    claims = []
    seen_texts = set()
    for art in raw:
        outlet = art.get("fact_check_outlet")
        topic = art.get("topic", "")
        for c in art.get("claims", []):
            ct = (c.get("claim_text") or "").strip()
            if not ct or ct in seen_texts:
                continue
            seen_texts.add(ct)
            claims.append({
                "claim_id": len(claims),
                "claim_text": ct,
                "claim_source": (c.get("claim_source") or "(unknown)")[:80],
                "fact_check_outlet": outlet,
                "topic": topic,
            })
    print(f"[normalize] clustering {len(claims)} unique claim-texts in chunks of {chunk_size}")

    # Sort by topic so within-batch clustering has more semantic coherence
    # (cross-batch duplicates still get merged by fuzzy match).
    claims_sorted = sorted(claims, key=lambda c: (c.get("topic") or "", c["claim_id"]))

    # Per-batch LLM clustering
    all_batch_families = []
    n_batches = (len(claims_sorted) + chunk_size - 1) // chunk_size
    for i in range(0, len(claims_sorted), chunk_size):
        batch = claims_sorted[i:i + chunk_size]
        bnum = i // chunk_size + 1
        print(f"[normalize] batch {bnum}/{n_batches} ({len(batch)} claims)")
        all_batch_families.extend(cluster_batch(batch))

    # Cross-batch merge
    print(f"\n[normalize] {len(all_batch_families)} per-batch families → merging by canonical-claim fuzzy match")
    merged = merge_families(all_batch_families)
    print(f"[normalize] merged into {len(merged)} global families")

    # Assign global ids and validate coverage
    families = []
    all_assigned = []
    for i, m in enumerate(merged):
        fam = {
            "id": i + 1,
            "canonical_claim": m["canonical_claim"],
            "member_ids": sorted(m["member_ids"]),
        }
        families.append(fam)
        all_assigned.extend(fam["member_ids"])

    all_claim_ids = {c["claim_id"] for c in claims}
    assigned_set = set(all_assigned)
    missing = all_claim_ids - assigned_set
    dupes = [x for x in all_assigned if all_assigned.count(x) > 1]
    print(f"[normalize] coverage: {len(assigned_set)}/{len(all_claim_ids)} claims assigned")
    if missing:
        print(f"  ⚠ unassigned claim_ids: {sorted(missing)}")
    if dupes:
        print(f"  ⚠ claims assigned to multiple families: {sorted(set(dupes))}")

    # Cross-reference family members with the original claims so output is self-contained
    claims_by_id = {c["claim_id"]: c for c in claims}
    for fam in families:
        fam["members"] = []
        for cid in fam["member_ids"]:
            if cid in claims_by_id:
                c = claims_by_id[cid]
                fam["members"].append({
                    "claim_id": cid,
                    "claim_text": c["claim_text"],
                    "claim_source": c["claim_source"],
                    "fact_check_outlet": c["fact_check_outlet"],
                    "topic": c["topic"],
                })

    with open(OUTPUT_FAMILIES, "w") as f:
        json.dump({"families": families}, f, indent=2)
    print(f"[write] {OUTPUT_FAMILIES}")

    # Filter to women's-health-relevant families for Stage 4a input
    kept = [f for f in families if WOMENS_HEALTH_RX.search(f["canonical_claim"])]
    dropped = [f for f in families if not WOMENS_HEALTH_RX.search(f["canonical_claim"])]
    with open(OUTPUT_FILTERED, "w") as f:
        json.dump({"families": kept}, f, indent=2)
    print(f"[write] {OUTPUT_FILTERED} — kept {len(kept)} women's-health families, dropped {len(dropped)} off-topic")

    print("\n=== Canonical claim families (top 20 by member count) ===")
    for fam in sorted(families, key=lambda x: -len(x.get("member_ids", [])))[:20]:
        print(f"\n[family {fam['id']}] ({len(fam['member_ids'])} members)")
        print(f"  canonical: {fam['canonical_claim']}")
        for m in fam.get("members", [])[:3]:
            print(f"    - [{m['topic']}] {m['claim_text'][:100]}")
        if len(fam.get("members", [])) > 3:
            print(f"    ... and {len(fam['members'])-3} more")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                    help=f"Claims per LLM call (default {DEFAULT_CHUNK_SIZE})")
    args = ap.parse_args()
    run(chunk_size=args.chunk_size)
