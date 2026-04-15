import csv
import sys
import pandas as pd
import subprocess
import json
import time
import re

# Raise max CSV field size limit to handle long text fields
csv.field_size_limit(2**30)

# File paths
INPUT_RAW = "womens_health_articles_text.csv"
INPUT_CLEANED = "womens_health_articles_text_clean.csv"
BAD_ROWS = "bad_rows.csv"
OUTPUT_CSV = "misinfo_flagged_output.csv"

# Optional: preprocess and clean malformed CSV rows
def preprocess_csv(input_path, cleaned_path, bad_path):
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False, on_bad_lines='skip')
    expected_cols = df.columns.tolist()
    df["__col_count"] = df.apply(lambda r: len(r), axis=1)

    good_df = df[df["__col_count"] == len(expected_cols)].drop(columns="__col_count")
    bad_df = df[df["__col_count"] != len(expected_cols)].drop(columns="__col_count")

    good_df.to_csv(cleaned_path, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
    bad_df.to_csv(bad_path, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")

    print(f"[OK] Preprocessing complete: {len(good_df)} good rows, {len(bad_df)} bad rows")

# Improved LLM call with text output parsing and retry logic
def call_llm(text, max_retries=3):
    prompt = f"""You are a fact-checking assistant. Analyze the following article and clearly state whether it is misleading or not, followed by a brief reason.

ARTICLE:
\"\"\"{text}\"\"\"

Example Output:
Misleading: True
Reason: This article incorrectly claims that emergency contraception causes abortions.
"""

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["ollama", "run", "llama3.2", prompt],
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace"
            )

            if result.returncode != 0:
                continue

            response = result.stdout.strip()

            misleading_match = re.search(r"Misleading\s*:\s*(True|False)", response, re.IGNORECASE)
            reason_match = re.search(r"Reason\s*:\s*(.*)", response, re.IGNORECASE | re.DOTALL)

            if not misleading_match or not reason_match:
                continue

            misleading = misleading_match.group(1).strip().lower() == "true"
            reason = reason_match.group(1).strip()

            if reason:
                return {
                    "misleading": misleading,
                    "reason": reason
                }
        except Exception:
            continue

    return None

# Core analysis logic
def format_hms(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"

def run_llm_analysis_only(input_file, output_file, max_rows=None):
    df = pd.read_csv(input_file, dtype=str, keep_default_na=False, encoding="utf-8")
    if max_rows:
        df = df.head(max_rows)
    total = len(df)
    start_time = time.time()

    flagged = []
    processed = 0
    for _, row in df.iterrows():
        article_text = row.get("full_text", "")
        if len(article_text.split()) < 100:
            continue

        result = call_llm(article_text)
        processed += 1
        if result is None:
            continue

        row["misleading"] = "True" if result.get("misleading") else "False"
        row["reason"] = result.get("reason")
        flagged.append(row)

        if processed % 10 == 0:
            elapsed = time.time() - start_time
            avg_time = elapsed / processed
            remaining = avg_time * (total - processed)
            print(f"Processed {processed}/{total} rows | Elapsed: {format_hms(elapsed)} | Remaining: {format_hms(remaining)} | Avg/row: {avg_time:.2f}s")

    pd.DataFrame(flagged).to_csv(output_file, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
    print(f"[OK] Analysis complete. Output saved to {output_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rows", type=int, default=None, help="Limit number of rows to process (for testing)")
    args = parser.parse_args()

    preprocess_csv(INPUT_RAW, INPUT_CLEANED, BAD_ROWS)
    run_llm_analysis_only(INPUT_CLEANED, OUTPUT_CSV, max_rows=args.max_rows)
