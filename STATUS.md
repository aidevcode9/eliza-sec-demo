# STATUS.md — SEC Filing RAG Assessment

> What is actually working right now. Not what is planned.
> Update this file based on reality, not aspiration.

**Panel:** Thursday April 10, 2026 — 9:15 AM PT (12:15 PM ET)
**Timebox:** ~4 hours build

---

## 1. Demo Readiness — Green When All True

- [ ] I can run ingestion from scratch on the full corpus
- [ ] I can start the app locally (API + frontend)
- [ ] I can ask one live question and get a cited answer
- [ ] The answer is grounded in actual filing text
- [ ] Citations show ticker, filing type, date, section
- [ ] Refusal works on an out-of-scope question
- [ ] I can explain architecture in under 2 minutes
- [ ] I can explain tradeoffs and roadmap in under 1 minute
- [ ] Docs match what the code actually does

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
- [x] Golden eval set: 10 real questions with verified expected answers
- [x] Adversarial eval set: 7 questions (injection, out-of-scope, speculative)
- [x] DECISIONS.md updated with 6 timestamped entries

### Not working yet

- [ ] Corpus not ingested
- [ ] Retrieval not tested
- [ ] Generation not tested
- [ ] Frontend not built
- [ ] No prompt iterations done

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
| **0** | Corpus analysis + eval set | ✅ Done | Human reviews eval questions |
| **1** | Ingestion pipeline | ⬜ | Human spot-checks chunks |
| **2** | Retrieval | ⬜ | Human reviews retrieval results |
| **3** | Generation (single LLM call) | ⬜ | Human reviews 3 answers |
| **4** | Citation validation | ⬜ Priority 3 | If time permits |
| **5** | Pipeline + API | ⬜ | Example request works |
| **6** | Evaluation | ⬜ | Results documented honestly |
| **7** | Frontend | ⬜ | UI question → cited answer |
| **8** | Polish + presentation | ⬜ | All deliverables complete |

---

## 4. Next 5 Tasks

_Keep this brutally short and current._

1. [x] Unzip corpus into data/. Analyze structure.
2. [x] Identify XBRL boundary and section headers across filings
3. [x] Write 10 real eval questions + 7 adversarial from actual corpus content
4. [ ] Build ingestion: strip XBRL, chunk by section, embed
5. [ ] Test retrieval on eval questions. Check multi-company balance.

---

## 5. Deliverables Checklist

### Required by assignment

| Deliverable | File | Status |
|-------------|------|--------|
| README with setup/run | README.md | ✅ Template |
| Indexing/retrieval code | src/ | ⬜ Scaffolded |
| Prompt iteration log | PROMPT_LOG.md | ✅ Template |
| Final prompt template | src/generate.py | ⬜ Scaffolded |
| Frontend | frontend/app.py | ⬜ Not started |
| Example request | README.md curl | ⬜ Not tested |
| Quality evaluation notes | DECISIONS.md + evals/ | ⬜ Placeholder |

### Panel presentation

| Deliverable | File | Status |
|-------------|------|--------|
| Engagement brief | docs/ENGAGEMENT_BRIEF.md | ✅ Template |
| Design decisions | DECISIONS.md | ✅ Template |
| Eval results table | ENGAGEMENT_BRIEF.md §4 | ⬜ No data yet |
| Demo questions (3) | STATUS.md §7 | ⬜ Not selected |

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
| 6 | Eval scope | 8-10 real questions, not 15+ aspirational | 4-hour build. Quality over quantity |

---

## 7. Demo Questions

_Select and test 3 questions for the live walkthrough._

| Slot | Question | Tested | Result |
|------|----------|--------|--------|
| Single-company | _TBD_ | ☐ | |
| Cross-company | _TBD_ | ☐ | |
| Refusal / fallback | _TBD_ | ☐ | |

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
