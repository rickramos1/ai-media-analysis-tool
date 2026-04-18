#!/bin/bash
set -e
cd /home/rickramos1/projects/ai_media_analysis_tool
source .venv/bin/activate

echo "=============================================="
echo "STAGE 0: preprocess CSV"
echo "=============================================="
python -c "from misinfo_detector import preprocess_csv; preprocess_csv('womens_health_articles_text.csv','womens_health_articles_text_clean.csv','bad_rows.csv')"

echo "=============================================="
echo "STAGE 1: article classifier"
echo "=============================================="
python -u article_classifier.py

echo "=============================================="
echo "STAGE 2: claim extractor"
echo "=============================================="
python -u claim_extractor.py

echo "=============================================="
echo "STAGE 3: ideology filter + auth-solo promotion"
echo "=============================================="
python -u stage3_filter.py

echo "=============================================="
echo "STAGE 3.5: claim normalizer (families + filter)"
echo "=============================================="
python -u claim_normalizer.py

echo "=============================================="
echo "STAGE 4a: embedding retrieval"
echo "=============================================="
# Unload qwen3, load nomic-embed
curl -s -X POST http://192.168.86.24:11434/api/generate -H 'Content-Type: application/json' -d '{"model":"qwen3:14b","keep_alive":0}' > /dev/null
python -u stage4a_retrieval.py

echo "=============================================="
echo "PIPELINE STAGES 1-4a COMPLETE"
echo "=============================================="
