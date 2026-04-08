# CLAUDE.md — SEC Filing RAG Assignment

> Trustworthy RAG for SEC filing analysis.
> Final demo configuration: small, grounded, and panel-ready.

---

## Project Principles

1. **Every answer must cite source filing, company, filing date, and section.** No exceptions.
2. **Prefer explicit confidence over silent failure.** Insufficient evidence should produce a refusal; weak evidence may still surface as a low-confidence answer with clear citations.
3. **One final answer call.** Retrieval and prompt assembly may happen beforehand, but the final answer must come from exactly one LLM call.
4. **Build the smallest trustworthy solution.** No overbuilding.
5. **Document meaningful decisions.** DECISIONS.md and PROMPT_LOG.md are required deliverables.
6. **Optimize for demo readiness.** Working software and honest documentation matter more than process ceremony.

---

## Architecture

```text
User Question
  → Injection check (basic prompt injection filter)
  → Embed query (text-embedding-3-large)
  → Retrieve (hybrid: BM25 + vector + RRF, top-k)
  → Generate answer (single LLM call, flat JSON output + top-level citations)
  → Citation validation (if enabled)
  → Return answer + citations OR refusal
```

---

## Project Structure

```text
sec-rag-assignment/
├── CLAUDE.md              ← this file
├── README.md              ← setup + run instructions
├── DECISIONS.md           ← timestamped design decisions
├── PROMPT_LOG.md          ← prompt iteration history
├── pyproject.toml         ← uv project config + dependencies
├── src/
│   ├── config.py          ← env vars, thresholds, model settings
│   ├── ingest.py          ← SEC filing loading + chunking + embedding
│   ├── retrieve.py        ← hybrid search + ticker-aware retrieval
│   ├── generate.py        ← single-call answer with citation enforcement
│   ├── validate.py        ← citation validation
│   ├── pipeline.py        ← orchestrator
│   ├── api.py             ← FastAPI endpoints
│   └── telemetry.py       ← traced LLM wrapper
├── evals/
│   ├── golden_set.json    ← demo-scoped golden questions
│   ├── adversarial.json   ← refusal / injection / out-of-scope tests
│   └── runner.py          ← eval runner
├── docs/
│   └── ENGAGEMENT_BRIEF.md
├── frontend/
│   └── app.py             ← Streamlit frontend
└── data/                  ← corpus input (gitignored)
```

---

## Non-Negotiable Rules

| Rule | Why |
|------|-----|
| Every substantive answer includes citations | Trust bar |
| Insufficient evidence → refusal; weak evidence → low-confidence answer or refusal | Trust bar |
| No hallucinated citations | Citation validation + prompt constraints |
| All final answers come from one `traced_llm_call()` | Assignment constraint |
| DECISIONS.md captures meaningful scope / architecture choices | Required deliverable |
| PROMPT_LOG.md reflects real prompt changes | Required deliverable |

---

## Documentation Protocol

### DECISIONS.md
Update after meaningful choices such as:
- chunking strategy
- retrieval strategy
- citation design
- model / framework decisions
- evaluation scope changes
- roadmap deferrals

Format:
```text
## YYYY-MM-DD HH:MM — [Short Title]
Decision: [what was decided]
Reasoning: [why]
Alternative considered: [what was not chosen]
Risk: [what could go wrong]
```

### PROMPT_LOG.md
Update after each material prompt change.

Format:
```text
## Version [N] — [Short description]
What changed: [specific prompt change]
Why: [problem this addressed]
Result: [observed impact]
```

---

## Build Workflow

1. Keep REQUIREMENTS.md aligned to what the demo needs.
2. Keep STATUS.md or equivalent reality-tracking aligned to what actually works.
3. Prioritize ingestion, retrieval, one-call generation, citations, and frontend.
4. Keep docs synchronized with the shipped demo configuration.
5. Rehearse the live demo path before polishing secondary features.

---

## SEC Filing Specifics

### Corpus
- Provided assessment corpus: **246 SEC filings** (89 10-K, 157 10-Q) across 54 companies
- Files are `.txt` with metadata header + XBRL/noisy leading text + filing content
- Strip noisy leading text before chunking
- Preserve metadata from file header and filename: ticker, filing type, filing date, quarter/report period when available

### Chunking strategy
- Primary: chunk by SEC section boundaries (Item 1, Item 1A, Item 7, etc.)
- Secondary: sub-chunk large sections with overlap
- Every chunk carries metadata: ticker, filing_type, filing_date, section_name

### Citation style
- Cite by **ticker, filing type, filing date, and section**
- Do **not** use page numbers for the `.txt` corpus

---

## Key Settings (final demo intent)

| Setting | Default / Intent | Notes |
|---------|------------------|-------|
| `CONFIDENCE_THRESHOLD` | `0.0` | No hard RRF threshold in demo build |
| `TOP_K` | `5` | Retrieve top-k evidence chunks |
| `CHUNK_SIZE` | `1000` | Demo configuration for better fact retrieval |
| `CHUNK_OVERLAP` | `200` | Preserve local context |

**Important:** RRF is a ranking signal, not a calibrated confidence score. Hard filtering is deferred until broader post-demo evaluation.

---

## Quick Start

```bash
uv sync
export OPENAI_API_KEY=your-key
mkdir -p data
unzip edgar_corpus.zip -d data/

uv run python -m src.ingest
uv run python evals/runner.py
uv run uvicorn src.api:app --reload --port 8000
uv run streamlit run frontend/app.py
```

---

## Final Reminder

This repo should read like a **truthful demo snapshot**:
- what is built
- how it works
- what was tested
- what was intentionally deferred
