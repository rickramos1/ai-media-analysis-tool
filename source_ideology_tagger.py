import csv
import argparse
from urllib.parse import urlparse

# Hardcoded ideology map
IDEOLOGY_MAP = {
    "foxnews.com": "Right",
    "breitbart.com": "Right",
    "dailywire.com": "Right",
    "inquirer.com": "Center-Left",
    "nytimes.com": "Left",
    "cnn.com": "Left",
    "washingtonpost.com": "Left",
    "npr.org": "Center-Left",
    "msnbc.com": "Left",
    "wsj.com": "Center-Right",
    "usatoday.com": "Center",
    "theguardian.com": "Left",
    "politico.com": "Center",
    "reuters.com": "Center",
    "apnews.com": "Center",
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
                print(f"⚠️ Row {i}: empty or malformed — skipping")
                continue

            media_url_raw = row.get("media_url") or row.get("media_name")
            domain = normalize_domain(media_url_raw)
            if not domain:
                row["ideology"] = "Unknown"
                print(f"⚠️ Row {i}: 'media_name' missing or unparseable → tagged as 'Unknown'")
                rows.append(row)
                continue

            ideology = IDEOLOGY_MAP.get(domain, "Unknown")
            row["ideology"] = ideology

            if ideology == "Unknown":
                unmatched_sources.add(domain)

            rows.append(row)

    print(f"✅ Tagged {len(rows)} articles with ideology.")
    print(f"⚠️ {len(unmatched_sources)} unmatched sources. Logged to 'unmatched_sources.txt'.")

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
