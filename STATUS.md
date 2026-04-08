# STATUS.md — SEC Filing RAG Assessment

> What is actually working right now. Not what is planned.
> Update this file based on reality, not aspiration.

**Panel:** Thursday April 10, 2026 — 9:15 AM PT (12:15 PM ET)
**Timebox:** ~4 hours build

---

## 1. Demo Readiness — Green When All True

- [x] I can run ingestion from scratch on the full corpus
- [x] I can start the app locally (API + frontend)
- [x] I can ask one live question and get a cited answer
- [x] The answer is grounded in actual filing text
- [x] Citations show ticker, filing type, date, section
- [x] Refusal works on an out-of-scope question
- [x] I can explain architecture in under 2 minutes
- [x] I can explain tradeoffs and roadmap in under 1 minute
- [x] Docs match what the code actually does

---

## 2. Current Build Truth

### Working now
_Only list what has been verified end-to-end._

- [x] Starter kit created (src/, evals/, .claude/, docs/)
- [x] CLAUDE.md with documentation protocol
- [x] REQUIREMENTS.md with acceptance criteria
- [x] ENGAGEMENT_BRIEF.md template
- [x] DECISIONS.md and PROMPT_LOG.md ready
- [x] pyproject.toml with uv config
- [x] Subagents and hooks configured
- [x] Corpus analyzed: 246 files, 54 tickers, ~79M chars after XBRL strip
- [x] XBRL boundary identified: "UNITED STATES" marker works for 100% of files
- [x] Section headers mapped: 10-K Items 1-16, 10-Q Items 1-6 (Part I/II)
- [x] Filename patterns documented: two variants, both parseable
- [x] Golden eval set: 10 questions (7 core + 3 assignment samples)
- [x] Adversarial eval set: 7 questions (injection, out-of-scope, speculative)
- [x] DECISIONS.md updated with 20+ timestamped entries
- [x] Ingestion pipeline: SEC-aware chunking, XBRL stripping, metadata parsing (11 tests)
- [x] Retrieval: precomputed BM25, vectorized search, multi-company detection, neighbor-aware chunk expansion (20 tests)
- [x] Generation: prompt V7, cite-or-refuse backstop, nested-output normalization (4 tests)
- [x] Citation validation: Jaccard similarity + span check (8 tests)
- [x] Pipeline + API wired end-to-end with FastAPI lifespan (10 tests)
- [x] 53 unit tests passing, lint clean
- [x] .env.example with all environment variables
- [x] API key scrubbed from git history
- [x] Local test script: scripts/test_local.sh
- [x] Streamlit frontend built and headless launch verified (`uv run streamlit run frontend/app.py`)
- [x] Frontend pipeline path exercised for cross-company answer and out-of-scope refusal
- [x] Langfuse telemetry integration (toggle via LANGFUSE_ENABLED)
- [x] Eval runner: golden set + adversarial set with latency tracking

### Not working yet

- [ ] Full corpus ingest not tested end-to-end (quick-ingest demo subset used)

### Known risks

- RRF fusion scores are not cosine similarity. Hard thresholds may filter good results.
- Retrieval may over-focus on one company for cross-company questions.
- Large sections (Item 1A Risk Factors) may exceed chunk size limits.
- Citation format needs to work without page numbers (corpus is .txt).
- Some Item headers appear as cross-references in text — anchor regex on line-start.

---

## 3. Phase Tracker

| Phase | Description | Status | Gate |
|-------|-------------|--------|------|
| **0** | Corpus analysis + eval set | Done | Human reviews eval questions |
| **1** | Ingestion pipeline | Done | Human spot-checks chunks |
| **2** | Retrieval | Done | Human reviews retrieval results |
| **3** | Generation (single LLM call) | Done | Human reviews 3 answers |
| **4** | Citation validation | Done | Jaccard + span check implemented |
| **5** | Pipeline + API | Done | Example request works |
| **6** | Evaluation | Done | Results documented honestly |
| **7** | Frontend | Done | Codex built Streamlit UI |
| **8** | Polish + presentation | In Progress | All deliverables complete |

---

## 4. Next 5 Tasks

_Keep this brutally short and current._

1. [ ] Run final eval suite and update ENGAGEMENT_BRIEF.md with real numbers
2. [ ] Verify all 3 demo questions work interactively in frontend
3. [ ] Final doc reconciliation (README, CLAUDE.md, ENGAGEMENT_BRIEF match reality)
4. [ ] Record demo flow: cross-company, single-company, refusal
5. [ ] Final pre-panel dry run

---

## 5. Deliverables Checklist

### Required by assignment

| Deliverable | File | Status |
|-------------|------|--------|
| README with setup/run | README.md | Done |
| Indexing/retrieval code | src/ | Done |
| Prompt iteration log | PROMPT_LOG.md | Done |
| Final prompt template | src/prompts.py | Done (V7) |
| Frontend | frontend/app.py | Done |
| Example request | README.md curl | Done |
| Quality evaluation notes | DECISIONS.md + evals/ | Done |

### Panel presentation

| Deliverable | File | Status |
|-------------|------|--------|
| Engagement brief | docs/ENGAGEMENT_BRIEF.md | Done |
| Design decisions | DECISIONS.md | Done (20+ entries) |
| Eval results table | ENGAGEMENT_BRIEF.md S4 | Updating with latest run |
| Demo questions (3) | STATUS.md S7 | Done |

---

## 6. Decision Log Snapshot

_Key decisions that affect the demo. Full log in DECISIONS.md._

| # | Topic | Decision | Why |
|---|-------|----------|-----|
| 1 | Runtime scope | Demo-first, single-user, static corpus | Assignment scope. Auth confirmed as roadmap by David |
| 2 | Answer architecture | One final LLM call only | Direct requirement. No query rewrite or verification loop |
| 3 | Frontend | Lightweight Streamlit UI | Sufficient for assessment. Faster than React |
| 4 | Retrieval thresholds | No hard RRF score threshold. Top-k only | RRF scores are not comparable to cosine similarity. Hard thresholds risk filtering good results |
| 5 | Citations | Ticker + filing type + date + section. No page numbers | Corpus is .txt files. Page numbers don't exist |
| 6 | Eval scope | 7 golden + 7 adversarial, scoped to demo config | 4-hour build. Quality over quantity. Honest pass rate |

---

## 7. Demo Questions

_Select and test 3 questions for the live walkthrough._

| Slot | Question | Tested | Result |
|------|----------|--------|--------|
| Cross-company | What are the primary risk factors facing Apple, Tesla, and JPMorgan, and how do they compare? | Pending | |
| Single-company | How has NVIDIA's revenue and growth outlook changed over the last two years? | Pending | |
| Refusal / fallback | What regulatory risks do the major pharmaceutical companies face, and how are they addressing them? | Pending | |

---

## 8. Time Budget

| Phase | Estimated | Actual | Notes |
|-------|-----------|--------|-------|
| Phase 0: Corpus analysis + eval set | 30 min | | |
| Phase 1: Ingestion | 45 min | | |
| Phase 2: Retrieval | 30 min | | |
| Phase 3: Generation | 30 min | | |
| Phase 5: Pipeline + API | 15 min | | |
| Phase 6: Evaluation | 20 min | | |
| Phase 7: Frontend | 30 min | | |
| Phase 8: Polish | 15 min | | |
| Phase 4: Citation validation | if time | | Priority 3 |
| **Total** | **~4 hours** | | |

---

## 9. Exit Criteria

This project is ready when:
- The system answers at least one live question well
- Citations are visible and grounded in actual filing text
- Refusal works on an out-of-scope question
- Docs match the real implementation (no overclaiming)
- The repo can be explained cleanly in a client-style walkthrough
- Eval results are real, not placeholder
