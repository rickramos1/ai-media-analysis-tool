import csv
import argparse
from urllib.parse import urlparse

csv.field_size_limit(2**30)

# Hardcoded ideology map
IDEOLOGY_MAP = {
    # Right
    "foxnews.com": "Right",
    "breitbart.com": "Right",
    "dailywire.com": "Right",
    "dailysignal.com": "Right",
    "townhall.com": "Right",
    "dailycaller.com": "Right",
    "nypost.com": "Right",
    "spectator.org": "Right",
    "pjmedia.com": "Right",
    "redstate.com": "Right",
    "patriotpost.us": "Right",
    "ncregister.com": "Right",
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
    # Left
    "nytimes.com": "Left",
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
    print(f"[WARN] {len(unmatched_sources)} unmatched sources. Logged to 'unmatched_sources.txt'.")

    with open(output_file, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    with open("unmatched_sources.txt", "w", encoding="utf-8") as f:
        for source in sorted(unmatched_sources):
            f.write(source + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--infile", required=True, help="Path to input CSV with media_name field")
    parser.add_argument("--outfile", required=True, help="Path to save output with ideology column")
    args = parser.parse_args()

    tag_ideology(args.infile, args.outfile)
