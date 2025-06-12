import csv
import time
import argparse
import json
import requests

OLLAMA_MODEL = "llama3.2"
OLLAMA_URL = "http://localhost:11434/api/generate"

def analyze_text_with_llm(text):
    if len(text.split()) < 30:
        return None, "Skipped: too short (<30 words)"

    prompt = f"""
You are an expert misinformation analyst. Review the following news article and respond ONLY in strict JSON format with two fields: 
- misleading: true or false
- reason: a brief explanation

ARTICLE:
{text}
"""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        })
        print(f"[DEBUG] HTTP status: {response.status_code}")
        print(f"[DEBUG] Raw API response:\n{response.text[:1000]}\n")

        result = response.json()
        raw_output = result.get("response", "{}").strip()
        print(f"[DEBUG] Raw LLM output:\n{raw_output}\n")

        parsed = json.loads(raw_output)
        return parsed.get("misleading"), parsed.get("reason")

    except Exception as e:
        print(f"[ERROR] Exception during LLM analysis: {e}")
        return None, f"Error or invalid JSON: {str(e)}"

def run_llm_analysis_only(input_file, output_file):
    print("🚀 LLM analysis starting...")
    with open(input_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"✅ Loaded {len(rows)} rows from {input_file}")

    final_rows = []
    for i, row in enumerate(rows, 1):
        text = row.get("full_text", "")
        misleading, reason = analyze_text_with_llm(text)
        row["misleading"] = misleading
        row["llm_reason"] = reason if reason is not None else "(no reason returned)"
        final_rows.append(row)
        print(f"[{i}/{len(rows)}] LLM → {misleading} | {row['llm_reason'][:50]}")
        time.sleep(1.5)

    with open(output_file, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=final_rows[0].keys())
        writer.writeheader()
        writer.writerows(final_rows)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--infile", required=True, help="Path to CSV with full_text")
    parser.add_argument("--outfile", required=True, help="Path to save output with LLM labels")
    args = parser.parse_args()

    run_llm_analysis_only(args.infile, args.outfile)
