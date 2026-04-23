"""Normalize specific debunked claim texts into canonical claim families.

Many debunked claims are restatements of the same underlying misinfo frame
(e.g., "Plan B causes abortions" ≈ "EC inhibits implantation" ≈ "IUDs are
abortifacients"). Stage 4a retrieves against these family-level canonicals
rather than literal quoted claims so it catches broader frames.

Outputs:
- claim_families.json           — all families
- claim_families_filtered.json  — families whose canonical claim is women's-health-relevant
                                  (drops off-topic claims that got in via contaminated
                                  fact-check roundups — ADHD meds, COVID, Medicaid, etc.)
"""
import json
import os
import re
import urllib.request

from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")

INPUT_CLAIMS = "claims.json"
OUTPUT_FAMILIES = "claim_families.json"
OUTPUT_FILTERED = "claim_families_filtered.json"

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
- Aim for 10–20 families. Claims with unique content can be their own family.

CLAIMS TO CLUSTER:
{claims_block}
"""


def call_llm(prompt, num_predict=4000):
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
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


def run():
    # Read the flat list of verified-source refutations from claims.json.
    # Each refutation is a distinct claim_text; assign a dense claim_id.
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
    print(f"[normalize] clustering {len(claims)} unique claim-texts")

    lines = []
    for c in claims:
        lines.append(f"  id={c['claim_id']} [topic={c['topic']}] [source={c['claim_source']}] {c['claim_text']}")
    prompt = PROMPT.format(claims_block="\n".join(lines))

    print("[normalize] calling LLM...")
    import time
    t0 = time.time()
    resp = call_llm(prompt)
    print(f"[normalize] LLM done in {time.time()-t0:.1f}s")

    parsed = extract_json(resp)
    if not parsed or "families" not in parsed:
        print("[ERROR] failed to parse response")
        print("Raw response:", repr(resp[:2000]))
        return

    families = parsed["families"]

    # Validate: every claim_id accounted for exactly once
    all_claim_ids = {c["claim_id"] for c in claims}
    assigned = []
    for fam in families:
        assigned.extend(fam["member_ids"])
    assigned_set = set(assigned)
    missing = all_claim_ids - assigned_set
    dupes = [x for x in assigned if assigned.count(x) > 1]

    print(f"\n[normalize] got {len(families)} families covering {len(assigned_set)}/{len(all_claim_ids)} claims")
    if missing:
        print(f"  ⚠ unassigned claim_ids: {sorted(missing)}")
    if dupes:
        print(f"  ⚠ duplicate assignments: {sorted(set(dupes))}")

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

    print("\n=== Canonical claim families ===")
    for fam in sorted(families, key=lambda x: -len(x.get("member_ids", []))):
        print(f"\n[family {fam['id']}] ({len(fam['member_ids'])} members)")
        print(f"  canonical: {fam['canonical_claim']}")
        for m in fam.get("members", [])[:3]:
            print(f"    - [{m['topic']}] {m['claim_text'][:100]}")
        if len(fam.get("members", [])) > 3:
            print(f"    ... and {len(fam['members'])-3} more")


if __name__ == "__main__":
    run()
