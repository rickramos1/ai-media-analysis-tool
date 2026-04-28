#!/bin/bash
set -e
cd "$(dirname "$0")"
source .venv/bin/activate

# Pick up OLLAMA_HOST + API keys from .env
set -a
[ -f .env ] && source .env
set +a
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

echo "=============================================="
echo "STAGE 0: preprocess CSV"
echo "=============================================="
PYTHONPATH=pipeline python -c "from misinfo_detector import preprocess_csv; preprocess_csv('data/womens_health_articles_text.csv','data/womens_health_articles_text_clean.csv','data/bad_rows.csv')"

echo "=============================================="
echo "STAGE 1: article classifier"
echo "=============================================="
python -u pipeline/article_classifier.py

echo "=============================================="
echo "STAGE 2: claim extractor"
echo "=============================================="
python -u pipeline/claim_extractor.py

echo "=============================================="
echo "STAGE 3: ideology filter + auth-solo promotion"
echo "=============================================="
python -u pipeline/stage3_filter.py

echo "=============================================="
echo "STAGE 3.5: claim normalizer (families + filter)"
echo "=============================================="
python -u pipeline/claim_normalizer.py

echo "=============================================="
echo "STAGE 4a: embedding retrieval"
echo "=============================================="
# Unload qwen3 from VRAM so nomic-embed-text can take its place
curl -s -X POST "$OLLAMA_HOST/api/generate" -H 'Content-Type: application/json' -d '{"model":"qwen3:14b","keep_alive":0}' > /dev/null
python -u pipeline/stage4a_retrieval.py

echo "=============================================="
echo "PIPELINE STAGES 1-4a COMPLETE"
echo "=============================================="
