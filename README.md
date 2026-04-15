# AI Media Analysis Tool

Analyzes media coverage of women's health topics for misinformation using the [MediaCloud](https://mediacloud.org/) API and local LLM-based fact-checking.

## What It Does

1. **Collects articles** from MediaCloud's public news archive across 5 topic areas: abortion misinformation, birth control myths, emergency contraception, mifepristone misinformation, and pregnancy crisis centers
2. **Scrapes full article text** from source URLs
3. **Detects misinformation** using a local LLM (ollama + llama3.2)
4. **Analyzes keyword trends** over time
5. **Tags sources by ideology** (left/center/right)

## Setup

```bash
# Create virtual environment
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Install mediacloud from GitHub (if pip install fails)
pip install git+https://github.com/mediacloud/api-client.git

# Configure API key
# Create a .env file with:
# MEDIACLOUD_API_KEY=your_key_here
```

For misinformation detection, install [ollama](https://ollama.ai/) and pull the model:
```bash
ollama pull llama3.2
```

## Pipeline

Run scripts in order:

```bash
# 1. Query MediaCloud for articles
python queries_public_collection_womens_health.py

# 2. Scrape full text from article URLs
python scrape_article_text.py

# 3. Run LLM misinformation detection
python misinfo_detector.py
# Optional: limit rows for testing
python misinfo_detector.py --max-rows 50

# 4. Analyze keyword trends over time
python keyword_analysis.py

# 5. Tag articles by source ideology
python source_ideology_tagger.py --infile womens_health_articles_text.csv --outfile tagged_output.csv
```

## Output Files

| File | Description |
|------|-------------|
| `womens_health_articles.csv` | Article metadata from MediaCloud |
| `womens_health_articles_text.csv` | Articles with scraped full text |
| `misinfo_flagged_output.csv` | Articles analyzed for misinformation |
| `keyword_trends.csv` | Weekly keyword frequency data |
| `keyword_trends.png` | Keyword trend chart |

## Project Structure

```
config.py                                    # MediaCloud API configuration
queries_public_collection_womens_health.py   # Step 1: Query articles
scrape_article_text.py                       # Step 2: Scrape article text
misinfo_detector.py                          # Step 3: LLM misinformation detection
keyword_analysis.py                          # Step 4: Keyword trend analysis
source_ideology_tagger.py                    # Step 5: Source ideology tagging
groups/                                      # Media source group definitions (JSON)
utils/media_utils.py                         # MediaCloud utility functions
```

## APIs and Tools

- **MediaCloud API v4** — article search and metadata
- **ollama + llama3.2** — local LLM for misinformation classification
- **BeautifulSoup** — article text extraction
- **pandas / matplotlib / seaborn** — data analysis and visualization
