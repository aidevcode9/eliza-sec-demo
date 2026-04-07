# SEC Filing RAG — Eliza Assessment

Trustworthy RAG for SEC filing analysis. Every answer cites source filings, or the system refuses.

**Corpus:** 246 SEC EDGAR filings (10-K and 10-Q) from 54 major US public companies, 2023-2025.

## Quick Start

```bash
# Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
uv sync

# Configure
export OPENAI_API_KEY=your-key-here

# Unzip corpus
mkdir -p data
unzip edgar_corpus.zip -d data/

# Ingest (chunk + embed + store)
uv run python -m src.ingest

# Run evals
uv run python evals/runner.py

# Start API
uv run uvicorn src.api:app --reload --port 8000

# Start frontend (separate terminal)
uv run streamlit run frontend/app.py
```

## Architecture

```
Question → Injection Check → Retrieve (BM25 + Vector + RRF) → Confidence Gate
  → Generate (single LLM call, cite-or-refuse) → Citation Validation → Response
```

**Core guarantee:** Every answer cites the specific filing, company, and section. If the system cannot find sufficient evidence, it refuses.

**Single API call constraint:** Indexing and retrieval run beforehand. The final answer comes from one LLM call.

## Project Structure

```
src/
  config.py      — thresholds + settings (all tunable)
  ingest.py      — load SEC filings, strip XBRL, chunk by section, embed
  retrieve.py    — hybrid search (BM25 + vector + RRF) + confidence gate
  generate.py    — single LLM call with citation enforcement
  validate.py    — citation validation (Jaccard + negation check)
  pipeline.py    — orchestrator (inject → retrieve → generate → validate)
  api.py         — FastAPI /v1/ask endpoint
  telemetry.py   — traced LLM/embedding wrapper
evals/
  golden_set.json    — curated Q&A pairs from SEC corpus
  adversarial.json   — out-of-scope + injection tests
  runner.py          — eval runner with pass/fail gate
docs/
  ENGAGEMENT_BRIEF.md — presentation brief for client meeting
frontend/
  app.py         — Streamlit frontend
```

## Deliverables

| Artifact | Location |
|----------|----------|
| Setup + run instructions | This file |
| Indexing + retrieval code | `src/` |
| Prompt iteration log | `PROMPT_LOG.md` |
| Final prompt template | `src/generate.py` |
| Frontend | `frontend/app.py` |
| Example request | See below |
| Quality evaluation notes | `DECISIONS.md` + `evals/` results |

## Example Request

```bash
curl -X POST http://localhost:8000/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the primary risk factors facing Apple and how have they changed over the past two years?"}'
```

## Quality Gates

```bash
uv run ruff check src/              # Lint
uv run python evals/runner.py       # Evals (80% golden set pass required)
```

## Key Design Decisions

See `DECISIONS.md` for the full timestamped log. Summary:

- **Section-based chunking** over sliding window (SEC filings have standard Item structure)
- **Hybrid search** (BM25 + vector + RRF) over vector-only (financial terms need lexical matching)
- **Confidence threshold at 0.70** (empirically tuned against golden set)
- **XBRL stripped** before chunking (machine-readable data pollutes embeddings)
- **Structured JSON output** with citations array (enforces citation at schema level)
- **Fail-closed** on low confidence (wrong SEC data answers have real consequences)
