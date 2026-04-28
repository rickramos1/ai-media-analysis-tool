import csv
import argparse
from urllib.parse import urlparse

csv.field_size_limit(2**30)

# Ideology tags follow AllSides / Ad Fontes-style buckets: Left, Center-Left,
# Center, Center-Right, Right. These are editorial-stance judgments, not
# factual-reliability ratings. Unknown means the outlet is not yet tagged.
IDEOLOGY_MAP = {
    # Right
    "foxnews.com": "Right",
    "breitbart.com": "Right",
    "dailycaller.com": "Right",
    "dailywire.com": "Right",
    "dailysignal.com": "Right",
    "townhall.com": "Right",
    "ncregister.com": "Right",
    "nypost.com": "Right",
    "spectator.org": "Right",
    "pjmedia.com": "Right",
    "redstate.com": "Right",
    "patriotpost.us": "Right",
    "newsbusters.org": "Right",
    "theblaze.com": "Right",
    # Center-Right
    "wsj.com": "Center-Right",
    "forbes.com": "Center-Right",
    "newsweek.com": "Center-Right",
    # Center
    "usatoday.com": "Center",
    "politico.com": "Center",
    "reuters.com": "Center",
    "apnews.com": "Center",
    "theconversation.com": "Center",
    "abcnews.go.com": "Center",
    "cbsnews.com": "Center",
    "nbcnews.com": "Center",
    "pbs.org": "Center",
    "benzinga.com": "Center",
    "factcheck.org": "Center",
    "staradvertiser.com": "Center",
    # Independent fact-check operations (IFCN-certified or equivalent;
    # editorial stance generally Center). Added when external fact-check
    # seed (pipeline/external_factchecks.py) surfaced these outlets.
    "politifact.com": "Center",
    "snopes.com": "Center",
    "factcheck.afp.com": "Center",
    "fullfact.org": "Center",
    "leadstories.com": "Center",
    "science.feedback.org": "Center",
    "africacheck.org": "Center",
    "boomlive.in": "Center",
    "firstcheck.in": "Center",
    "thip.media": "Center",
    "livescience.com": "Center",
    # Other outlets surfaced by the external pull
    "rollcall.com": "Center",
    "ajc.com": "Center",
    "realclearpolitics.com": "Center-Right",
    "mlive.com": "Center-Left",
    # Center-Left
    "inquirer.com": "Center-Left",
    "npr.org": "Center-Left",
    "politicalwire.com": "Center-Left",
    "bostonglobe.com": "Center-Left",
    "latimes.com": "Center-Left",
    "chicagotribune.com": "Center-Left",
    "seattletimes.com": "Center-Left",
    "denverpost.com": "Center-Left",
    "baltimoresun.com": "Center-Left",
    "sandiegouniontribune.com": "Center-Left",
    "mercurynews.com": "Center-Left",
    "sun-sentinel.com": "Center-Left",
    "pilotonline.com": "Center-Left",
    "courant.com": "Center-Left",
    "ocregister.com": "Center-Left",
    "twincities.com": "Center-Left",
    "orlandosentinel.com": "Center-Left",
    "newsday.com": "Center-Left",
    "jsonline.com": "Center-Left",
    "cleveland.com": "Center-Left",
    "stltoday.com": "Center-Left",
    "newyorker.com": "Center-Left",
    "scientificamerican.com": "Center-Left",
    "theverge.com": "Center-Left",
    "wired.com": "Center-Left",
    "theatlantic.com": "Center-Left",
    # Left
    "nytimes.com": "Left",
    "rollingstone.com": "Left",
    "cnn.com": "Left",
    "washingtonpost.com": "Left",
    "msnbc.com": "Left",
    "theguardian.com": "Left",
    "rawstory.com": "Left",
    "jezebel.com": "Left",
    "huffpost.com": "Left",
    "motherjones.com": "Left",
    "dailykos.com": "Left",
    "buzzfeed.com": "Left",
    "slate.com": "Left",
    "salon.com": "Left",
    "vox.com": "Left",
    "thenation.com": "Left",
    "nationalmemo.com": "Left",
    "talkingpointsmemo.com": "Left",
    "gizmodo.com": "Left",
    "alternet.org": "Left",
    "theintercept.com": "Left",
}

def normalize_domain(media_name):
    if not media_name:
        return None
    media_name = media_name.strip().lower()
    parsed = urlparse(media_name if media_name.startswith("http") else f"https://{media_name}")
    return parsed.netloc.replace("www.", "")

def tag_ideology(input_file, output_file):
    rows = []
    unmatched_sources = set()

    with open(input_file, "r", encoding="utf-8", newline='') as f:
        reader = csv.DictReader(f, quoting=csv.QUOTE_ALL, skipinitialspace=True)

        for i, row in enumerate(reader, 2):
            if row is None or len(row) == 0:
                print(f"[WARN] Row {i}: empty or malformed — skipping")
                continue

            media_url_raw = row.get("media_url") or row.get("media_name")
            domain = normalize_domain(media_url_raw)
            if not domain:
                row["ideology"] = "Unknown"
                print(f"[WARN] Row {i}: 'media_name' missing or unparseable → tagged as 'Unknown'")
                rows.append(row)
                continue

            ideology = IDEOLOGY_MAP.get(domain, "Unknown")
            row["ideology"] = ideology

            if ideology == "Unknown":
                unmatched_sources.add(domain)

            rows.append(row)

    print(f"[OK] Tagged {len(rows)} articles with ideology.")
    print(f"[WARN] {len(unmatched_sources)} unmatched sources. Logged to 'data/unmatched_sources.txt'.")

    with open(output_file, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    with open("data/unmatched_sources.txt", "w", encoding="utf-8") as f:
        for source in sorted(unmatched_sources):
            f.write(source + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--infile", required=True, help="Path to input CSV with media_name field")
    parser.add_argument("--outfile", required=True, help="Path to save output with ideology column")
    args = parser.parse_args()

    tag_ideology(args.infile, args.outfile)
