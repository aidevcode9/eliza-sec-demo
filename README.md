# SEC Filing RAG — Eliza Assessment

Trustworthy RAG for SEC filing analysis. Every answer includes source citations, or the system refuses.

**Corpus:** 246 SEC EDGAR filings (10-K and 10-Q) from 54 major US public companies, spanning 2023–2025.

**Note on the demo dataset:** The provided corpus contains 246 filings. The demo runs against the processed retrieval index built from that corpus.

## Quick Start

```bash
# Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup
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

```text
Question → Injection Check → Retrieve (BM25 + Vector + RRF, top-k)
  → Generate (single LLM call, flat JSON answer + top-level citations) → Citation Validation → Response
```

**Core guarantee:** Every answer cites the specific filing, company, filing date, and section. If the system cannot find sufficient evidence, it refuses.

**Single API call constraint:** Indexing and retrieval run beforehand. The final answer comes from one LLM call.

## Project Structure

```text
src/
  config.py      — thresholds + settings
  ingest.py      — load SEC filings, strip XBRL, chunk by section, embed
  retrieve.py    — hybrid search (BM25 + vector + RRF)
  generate.py    — single LLM call with citation enforcement
  validate.py    — citation validation
  pipeline.py    — orchestrator (inject → retrieve → generate → validate)
  api.py         — FastAPI /v1/ask endpoint
  telemetry.py   — traced LLM/embedding wrapper
evals/
  golden_set.json    — demo-scoped golden Q&A pairs from SEC corpus
  adversarial.json   — out-of-scope + injection tests
  runner.py          — eval runner
docs/
  ENGAGEMENT_BRIEF.md — panel / client walkthrough brief
frontend/
  app.py         — Streamlit frontend
```

## Deliverables

| Artifact | Location |
|----------|----------|
| Setup + run instructions | This file |
| Indexing + retrieval code | `src/` |
| Prompt iteration log | `PROMPT_LOG.md` |
| Final prompt template | `src/prompts.py` |
| Frontend | `frontend/app.py` |
| Example request | See below |
| Quality evaluation notes | `DECISIONS.md`, `TECHNICAL_NOTES.md`, and `evals/` |

## Example Request

```bash
curl -X POST http://localhost:8000/v1/ask   -H "Content-Type: application/json"   -d '{"question": "What are the primary risk factors facing Apple and how have they changed over the past two years?"}'
```

## Quality Checks

```bash
uv run ruff check src/              # Lint
uv run python evals/runner.py       # Report current scoped golden + adversarial results
```

## Key Design Decisions

See `DECISIONS.md` for the full timestamped log. Summary:

- **Section-based chunking** over generic sliding window (SEC filings have standard Item structure)
- **Hybrid search** (BM25 + vector + RRF) over vector-only (financial terms benefit from lexical matching)
- **No hard RRF threshold in the demo build** (RRF is a ranking signal, not a calibrated confidence score)
- **Refusal handled at generation time** when retrieved evidence is insufficient or ambiguous
- **XBRL / noisy leading text stripped** before chunking (machine-readable content pollutes retrieval)
- **Structured JSON output** with a plain-text `answer` field and top-level citations array
- **Backend normalization** for malformed nested multi-company output so the API and UI contract stay stable

## Scope Notes

This is a **demo-first assessment build**, not a production platform. Authentication, SSO/RBAC, and live corpus refresh are intentionally treated as roadmap items rather than in-scope build requirements.
