#!/usr/bin/env bash
# Local test script — runs everything that doesn't need an API key
set -e

echo "============================================"
echo "SEC Filing RAG — Local Test Suite"
echo "============================================"

echo ""
echo "--- 1. Lint check ---"
uv run ruff check src/ tests/

echo ""
echo "--- 2. Syntax check ---"
uv run python -m py_compile src/config.py src/ingest.py src/retrieve.py \
  src/generate.py src/validate.py src/pipeline.py src/api.py src/telemetry.py src/prompts.py

echo ""
echo "--- 3. Unit tests (no API key needed) ---"
uv run pytest tests/ -v

echo ""
echo "--- 4. Eval JSON validation ---"
uv run python -c "
import json
gs = json.load(open('evals/golden_set.json'))
adv = json.load(open('evals/adversarial.json'))
print(f'Golden set: {len(gs)} questions')
print(f'Adversarial: {len(adv)} questions')
print('JSON structure: OK')
"

echo ""
echo "--- 5. Import check (all modules load) ---"
uv run python -c "
from src.config import config
from src.ingest import Chunk, parse_metadata, parse_filename, strip_xbrl, split_sections
from src.retrieve import RetrievalIndex, retrieve, detect_query_tickers
from src.generate import generate_answer
from src.validate import validate_citations
from src.pipeline import ask
from src.prompts import SYSTEM_PROMPT
from src.telemetry import traced_llm_call, traced_embedding
print('All modules import OK')
print(f'Prompt version: V5 ({len(SYSTEM_PROMPT)} chars)')
print(f'Config: chunk_size={config.chunk_size}, top_k={config.top_k}, model={config.model_id}')
"

echo ""
echo "============================================"
echo "ALL LOCAL CHECKS PASSED"
echo "============================================"
echo ""
echo "To test with API key (requires OPENAI_API_KEY):"
echo "  uv run python -m src.ingest          # ingest corpus"
echo "  uv run python evals/runner.py        # run full evals"
echo "  uv run uvicorn src.api:app --port 8000  # start API"
