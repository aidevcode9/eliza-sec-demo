# CLAUDE.md — SEC Filing RAG Assignment

> Trustworthy RAG for SEC filing analysis. Phase-1 proof of value.
> Designed for speed: adapt to corpus, prove trust through evals, document every decision.

---

## Project Principles

1. **Every answer must cite source filing, company, section, and page.** No exceptions.
2. **If confidence is below threshold, REFUSE.** A confident wrong answer is worse than no answer.
3. **Fail-closed by default.** Missing data, failed retrieval, low confidence → refusal.
4. **Evals before features.** Write the golden set before optimizing retrieval.
5. **Build the smallest trustworthy solution.** No overbuilding.
6. **Document every decision.** DECISIONS.md and PROMPT_LOG.md are required deliverables.

---

## Architecture

```
User Question
  → Injection check (basic prompt injection filter)
  → Embed query (text-embedding-3-large)
  → Retrieve (hybrid: BM25 + vector, confidence threshold >= 0.70)
  → Generate answer (cite-or-refuse, structured JSON output)
  → Citation validation (verify cited text exists in retrieved chunks)
  → Return answer + citations OR refusal
```

---

## Project Structure

```
sec-rag-assignment/
├── CLAUDE.md              ← you are here
├── README.md              ← setup + run instructions
├── DECISIONS.md           ← timestamped design decisions (REQUIRED DELIVERABLE)
├── PROMPT_LOG.md          ← prompt iteration history (REQUIRED DELIVERABLE)
├── pyproject.toml         ← uv project config + dependencies
├── .python-version        ← python version pin
├── .claude/
│   ├── settings.json      ← hooks (pre-commit, post-edit)
│   ├── agents/            ← subagents for workflow
│   └── commands/          ← utility slash commands
├── src/
│   ├── config.py          ← env vars, thresholds, model settings
│   ├── ingest.py          ← document loading + chunking + embedding
│   ├── retrieve.py        ← hybrid search + confidence gate
│   ├── generate.py        ← LLM answer with citation enforcement
│   ├── validate.py        ← citation validation (Jaccard + span check)
│   ├── pipeline.py        ← orchestrator: ties ingest → retrieve → generate → validate
│   ├── api.py             ← FastAPI endpoints
│   └── telemetry.py       ← lightweight traced LLM wrapper
├── evals/
│   ├── golden_set.json    ← curated Q&A pairs with expected answers
│   ├── adversarial.json   ← out-of-scope / injection / trick questions
│   └── runner.py          ← eval runner with pass/fail gate
├── docs/
│   └── ENGAGEMENT_BRIEF.md ← consultant-style presentation brief
├── frontend/              ← Streamlit frontend
└── data/                  ← corpus goes here (gitignored)
```

---

## NON-NEGOTIABLE Rules

| Rule | Why |
|------|-----|
| Every answer includes citations array | Trust bar |
| Confidence < 0.70 → refusal | Fail-closed |
| Golden set evals pass before demo | Prove it works |
| No hallucinated citations | Citation validation checks span exists in source |
| All LLM calls through `traced_llm_call()` | Observability |
| DECISIONS.md updated after every design choice | Required deliverable |
| PROMPT_LOG.md updated after every prompt change | Required deliverable |

---

## Documentation Protocol

### DECISIONS.md — Update after EVERY design choice

After any of these events, immediately append to DECISIONS.md:
- Choosing a chunking strategy
- Changing a threshold or config value
- Adding, removing, or modifying a pipeline stage
- Choosing one library/tool over another
- Discovering something unexpected in the corpus
- Deciding NOT to build something

Format:
```
## YYYY-MM-DD HH:MM — [Short Title]
Decision: [what you decided]
Reasoning: [why]
Alternative considered: [what you didn't do]
Risk: [what could go wrong with this choice]
```

### PROMPT_LOG.md — Update after EVERY prompt change

After modifying the system prompt or adding/changing prompt instructions in generate.py, immediately append to PROMPT_LOG.md:

Format:
```
## Version [N] — [Short description of change]
What changed: [specific change to prompt text]
Why: [what problem this solves]
Result: [what improved or didn't — fill in after testing]
```

### Enforcement

These updates are NOT optional. They are required deliverables for the panel presentation. If you complete a task and did not update the relevant log, update it before reporting the task as complete.

---

## Build Process

### How work flows
1. Read `STATUS.md` — know where we are
2. Read `REQUIREMENTS.md` — know what to build next and the acceptance criteria
3. Build to the acceptance criteria for the current phase
4. Update `STATUS.md` when a requirement is complete
5. At phase gate, stop and wait for human review before proceeding

### Key files
| File | Purpose |
|------|---------|
| `STATUS.md` | Where we are. Current phase, now/next/done. Read first. |
| `REQUIREMENTS.md` | What to build. Acceptance criteria per requirement. |
| `DECISIONS.md` | Why we built it that way. Timestamped log. |
| `PROMPT_LOG.md` | Prompt iteration history. |
| `docs/ENGAGEMENT_BRIEF.md` | Panel presentation brief. Fill in eval results when available. |

---

## Auto-Trigger Protocol

### Before ANY implementation
1. Read this file
2. Read `STATUS.md` — what phase are we in?
3. Read `REQUIREMENTS.md` — what are the acceptance criteria for the current task?
4. Check `evals/golden_set.json` — does it exist and is it populated? If not, build it first.
5. Understand the corpus in `data/` — read 3-5 documents manually.
6. Check DECISIONS.md — is it current?

### Before ANY PR or "done" declaration
1. Run `uv run python evals/runner.py` — must show pass rate
2. Run `uv run ruff check src/` — must pass
3. Run `uv run pytest tests/ -v` if tests exist — must pass
4. Check: does every answer path produce citations or a refusal? No silent failures.
5. Verify DECISIONS.md has been updated since the last code change.
6. Verify PROMPT_LOG.md reflects the current prompt in generate.py.

---

## Subagent Protocol

| Agent | When to spawn |
|-------|---------------|
| `researcher` | Before implementing any new feature. Gathers context from corpus + codebase. |
| `coder` | After research brief approved. Implements with tests. Updates DECISIONS.md and PROMPT_LOG.md. |
| `eval-writer` | When touching retrieval, generation, or citation logic. Write eval FIRST. |
| `verifier` | After implementation. Runs lint + tests + eval suite. Checks docs are current. |
| `skeptic` | Before declaring done. Adversarial review: hallucination risks, citation gaps, refusal failures. |

---

## SEC Filing Specifics

### Corpus
- 246 SEC filings (89 10-K, 157 10-Q) from 54 companies
- Files are .txt with metadata header + XBRL data + filing content
- Strip XBRL data before chunking (everything before "Table of Contents" or first "Item" heading)
- Preserve metadata from file header: ticker, filing_type, filing_date
- Parse metadata from filename pattern: {TICKER}_{TYPE}_{DATE}_full.txt

### Chunking strategy
- Primary: chunk by SEC section boundaries (Item 1, Item 1A, Item 7, etc.)
- Secondary: sliding window within sections that exceed max chunk size
- Every chunk carries metadata: ticker, filing_type, filing_date, section_name

### Sample questions (from assignment)
- "What are the primary risk factors facing Apple, Tesla, and JPMorgan, and how do they compare?"
- "How has NVIDIA's revenue and growth outlook changed over the last two years?"
- "What regulatory risks do the major pharmaceutical companies face, and how are they addressing them?"

---

## Key Thresholds (tunable in config.py)

| Threshold | Default | Purpose |
|-----------|---------|---------|
| `CONFIDENCE_THRESHOLD` | 0.0 (disabled) | Do NOT hard-filter on RRF scores. Return top-k. Only enable if empirical testing shows noise |
| `JACCARD_THRESHOLD` | 0.30 | Citation validation minimum overlap (Phase 4, if time) |
| `TOP_K` | 5 | Max chunks retrieved |
| `CHUNK_SIZE` | 2000 | Target chunk size (chars) for within-section splits |
| `CHUNK_OVERLAP` | 200 | Overlap for within-section splits |

---

## Working With This Repo

### Quick start (using uv)
```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup project
uv sync

# Configure
export OPENAI_API_KEY=your-key

# Drop corpus into data/
mkdir -p data
unzip edgar_corpus.zip -d data/

# Ingest
uv run python -m src.ingest

# Run evals
uv run python evals/runner.py

# Start API
uv run uvicorn src.api:app --reload --port 8000

# Start frontend
uv run streamlit run frontend/app.py
```

---

## Mistakes Log

| Date | Mistake | Fix | Lesson |
|------|---------|-----|--------|
| | | | |
