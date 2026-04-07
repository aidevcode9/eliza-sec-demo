# REQUIREMENTS.md — SEC Filing RAG Assessment

> Build driver for the Eliza FDE panel assessment.
> Each requirement has acceptance criteria. Claude Code reads this to know what to build and when it's done.
> Human approves each phase before moving to the next.

---

## 1. Goal

Build a lightweight retrieval-augmented QA demo over the provided SEC filings corpus.

The system must:
- Accept a natural-language business question
- Retrieve relevant filing evidence from the provided corpus
- Produce the final answer in **one LLM API call**
- Return a structured, evidence-grounded answer with visible citations
- Be usable through a simple front-end demo

This is a **demo-first assessment build**, not a production platform.

---

## 2. Scope

### In scope
- Offline ingestion of the provided SEC corpus (246 .txt filings)
- Parsing filing text and metadata (ticker, filing type, date, section)
- Chunking filings into retrievable units (section-aware)
- Building a retrieval index (hybrid: BM25 + vector)
- Retrieving context for a user question
- Packing context into one final answer prompt
- One final LLM call for answer generation
- Returning structured answer + citations
- Simple Streamlit front-end for live demo
- Real evaluation set (8-10 questions) and quality notes
- Prompt iteration log and decision log

### Explicitly out of scope
- Authentication / login / SSO / RBAC
- Multi-user support or tenant isolation
- SharePoint / shared-drive connectors or live corpus sync
- Admin console
- Multi-step agent workflows
- Query rewriting via extra LLM calls
- Answer verification via extra LLM calls
- Production-grade telemetry dashboards
- Full deployment hardening
- Custom fine-tuned models

Items above belong in the phase-2 roadmap discussion, not the build.

---

## 3. Key Assumptions

- The provided corpus is the source of truth. Static for the build.
- Authentication is a roadmap item confirmed with David.
- Data update paths may be discussed but are not implemented.
- The runtime answer path must use exactly one LLM API request.
- Indexing, chunking, and retrieval preparation run before the answer call.
- A lightweight single-user Streamlit UI is sufficient.
- The corpus is .txt files, not PDFs. There are no page numbers. Cite by filing, section, and date.

---

## 4. Success Criteria

The build is successful if it can:

1. Answer at least one live business question end-to-end in the UI
2. Use retrieved filing evidence in a single final LLM call
3. Cite source filings clearly (ticker, filing type, date, section, supporting quote)
4. Handle at least:
   - One single-company factual question
   - One multi-company comparison question
   - One time-based comparison question
   - One insufficient-evidence / refusal case
5. Be explained clearly in a client-style walkthrough under 12 minutes

---

## 5. Top Risks

Manage these actively during the build:

| Risk | Mitigation |
|------|-----------|
| Noisy SEC text (XBRL headers) reduces retrieval quality | Strip XBRL before chunking. Verify with spot checks |
| Missing or incorrect metadata weakens comparison questions | Parse from both file header and filename. Cross-check |
| Retrieval over-focuses on one company for cross-company questions | Test multi-company retrieval early. Consider per-ticker retrieval if needed |
| RRF fusion scores are not comparable to cosine similarity. Hard thresholds may filter good results | Do NOT apply hard confidence threshold on RRF scores. Return top-k, let generation handle uncertainty. Tune only if empirical testing shows noise |
| Citation format unclear for text-based filings | Cite by ticker, filing type, date, section. No page numbers (corpus is .txt) |
| Docs overstate what the code actually does | STATUS.md tracks what actually works, not what is planned |
| Extra complexity violates single-call constraint | No query rewrite, no verification loop, no chained LLM calls |
| Demo fails on live question | Rehearse with 3 pre-tested questions. Have backup screenshots |

---

## 6. Phased Requirements

### Phase 0 — Corpus Analysis

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P0-1 | Analyze corpus structure | Read 5+ filings across different companies and types. Document file format, header, XBRL location, section patterns in DECISIONS.md | ☐ |
| P0-2 | Identify XBRL boundary | Find reliable text marker where XBRL ends and filing content begins. Test across 10+ files. Document in DECISIONS.md | ☐ |
| P0-3 | Map SEC section headers | List Item headers and how consistently they appear across 10-K vs 10-Q. Document in DECISIONS.md | ☐ |
| P0-4 | Parse filename metadata | Confirm pattern: {TICKER}\_{TYPE}\_{QUARTER}\_{DATE}\_full.txt or {TICKER}\_{TYPE}\_{DATE}\_full.txt. Document exceptions | ☐ |
| P0-5 | Estimate corpus size | Total chars after XBRL stripping. Average section sizes. Inform chunking decisions | ☐ |
| P0-6 | Write evaluation set | 8-10 questions covering: single-company factual, cross-company comparison, temporal, regulatory/risk, insufficient-evidence, adversarial. Save to evals/golden_set.json and evals/adversarial.json | ☐ |

**Gate:** Human reviews corpus analysis + evaluation set before Phase 1.

---

### Phase 1 — Ingestion Pipeline

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P1-1 | Load all .txt files from data/ | All 246 files loaded. Metadata parsed from file header AND filename | ☐ |
| P1-2 | Strip XBRL / noisy leading text | Content before filing start marker removed. Verified across 10+ files from different companies | ☐ |
| P1-3 | Section-aware chunking | Chunk by SEC Item boundaries when detectable. Paragraph-preserving where possible. Sliding window fallback for weak structure | ☐ |
| P1-4 | Within-section splitting | Sections exceeding max chunk size split with overlap. Section metadata preserved on sub-chunks | ☐ |
| P1-5 | Chunk metadata | Each chunk has: chunk_id, doc_name, ticker, filing_type, filing_date, report_period/quarter (if available), section_name, text. No page numbers | ☐ |
| P1-6 | Embed all chunks | Embeddings generated via traced_embedding(). Batched. Stored alongside metadata | ☐ |
| P1-7 | Persist to disk | Chunks + embeddings saved. Can be loaded without re-ingesting | ☐ |
| P1-8 | Runnable | `uv run python -m src.ingest` completes on full corpus. Logs total chunks, time | ☐ |
| P1-9 | Document decisions | All ingestion decisions in DECISIONS.md with timestamps | ☐ |

**Gate:** Human spot-checks chunks for 3 companies. Metadata correct. XBRL stripped. Sections identified.

---

### Phase 2 — Retrieval

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P2-1 | Vector search | Query embedded, cosine similarity against chunks, returns scored results | ☐ |
| P2-2 | BM25 search | Tokenized query matched against chunk text | ☐ |
| P2-3 | Hybrid fusion (RRF) | Vector + BM25 fused via Reciprocal Rank Fusion. Single ranked list | ☐ |
| P2-4 | Top-k without brittle thresholds | Return top-k results. Do NOT hard-filter on RRF scores. Let generation handle uncertainty. Only add threshold if empirical testing proves necessary | ☐ |
| P2-5 | Multi-company retrieval | Questions mentioning multiple tickers retrieve relevant chunks from each company, not just top-k from one | ☐ |
| P2-6 | Metadata in results | Each result includes ticker, filing_type, filing_date, section_name for citation | ☐ |
| P2-7 | Retrieval spot-check | Run 3+ golden set questions through retrieval only. Verify correct source docs appear in results | ☐ |
| P2-8 | Document decisions | Retrieval decisions in DECISIONS.md | ☐ |

**Gate:** Human reviews retrieval for 3 golden set questions. Correct filings in results. Multi-company not collapsed.

---

### Phase 3 — Generation (Single LLM Call)

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P3-1 | System prompt v1 | Answer from context only. Cite by ticker, filing type, date, section. Refuse if insufficient. Log in PROMPT_LOG.md | ☐ |
| P3-2 | Structured output | LLM returns JSON: answer, citations array (ticker, filing_type, filing_date, section, quoted_text), confidence, refusal_reason | ☐ |
| P3-3 | Cite-or-refuse | Empty or insufficient context → refusal with reason. No hallucinated answers | ☐ |
| P3-4 | Cross-company handling | Prompt organizes answer by company when question mentions multiple companies | ☐ |
| P3-5 | Single call constraint | Final answer from exactly one call to traced_llm_call(). No chained calls | ☐ |
| P3-6 | Prompt iteration | At least 3 prompt versions iterated against eval questions. Each version logged in PROMPT_LOG.md | ☐ |
| P3-7 | Injection handling | Injection attempts return refusal | ☐ |
| P3-8 | Document decisions | Generation decisions in DECISIONS.md | ☐ |

**Gate:** Human reviews 3 answers. Citations specific and verifiable. Refusal works on out-of-scope question.

---

### Phase 4 — Citation Validation (if time permits)

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P4-1 | Jaccard similarity check | Each citation's quoted_text checked against source chunk. Score calculated | ☐ |
| P4-2 | Substring match | Exact substring match attempted first | ☐ |
| P4-3 | Validation metadata | Each citation tagged: valid (bool), validation_note, jaccard_score | ☐ |
| P4-4 | Overall flag | Response includes citations_valid boolean | ☐ |

**Note:** This phase is Priority 3. Ship Phases 1-3 + 5-7 first. Add citation validation only if time remains.

---

### Phase 5 — Pipeline + API

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P5-1 | End-to-end pipeline | `pipeline.ask(question)` runs: inject check → retrieve → generate. Returns complete response | ☐ |
| P5-2 | API endpoint | `POST /v1/ask` accepts {"question": str}, returns response JSON | ☐ |
| P5-3 | Health endpoint | `GET /healthz` returns status and chunk count | ☐ |
| P5-4 | Example request | curl command in README that works against running API | ☐ |

**Gate:** Human runs example request. Gets cited answer.

---

### Phase 6 — Evaluation

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P6-1 | Run eval set | `uv run python evals/runner.py` runs all questions. Reports pass/fail per question + overall | ☐ |
| P6-2 | Coverage | Eval covers: single-company, cross-company, temporal, risk/regulatory, refusal, adversarial | ☐ |
| P6-3 | Results documented | For each question: expected evidence, actual answer quality, citation quality, pass/fail, known failure modes | ☐ |
| P6-4 | Results in brief | Eval results filled into docs/ENGAGEMENT_BRIEF.md section 4 with real numbers | ☐ |

**Gate:** Eval results documented. Honest about failures.

---

### Phase 7 — Frontend

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P7-1 | Streamlit app | Question input, submit button, answer display, citation display | ☐ |
| P7-2 | Citation rendering | Citations show ticker, filing type, date, section, and supporting quote. Human-readable, not JSON dump | ☐ |
| P7-3 | Refusal display | Refusal reason shown clearly when system refuses | ☐ |
| P7-4 | Loading state | Loading indicator while processing | ☐ |
| P7-5 | Pre-loaded example | Default question or quick-demo button | ☐ |
| P7-6 | Runnable | `uv run streamlit run frontend/app.py` works | ☐ |

**Gate:** Human asks question in UI, gets cited answer.

---

### Phase 8 — Polish + Presentation

| ID | Requirement | Acceptance Criteria | Status |
|----|-------------|-------------------|--------|
| P8-1 | DECISIONS.md complete | All decisions timestamped. Matches what was actually built | ☐ |
| P8-2 | PROMPT_LOG.md complete | All prompt iterations documented. Matches current prompt in generate.py | ☐ |
| P8-3 | ENGAGEMENT_BRIEF.md complete | Eval results filled in. All placeholders replaced with real numbers | ☐ |
| P8-4 | README accurate | Setup instructions work from clean clone. Deliverables listed. Does not overclaim | ☐ |
| P8-5 | Lint passes | `uv run ruff check src/` — zero errors | ☐ |
| P8-6 | Demo rehearsal | Talk through presentation once out loud. 12 minutes max | ☐ |
| P8-7 | Demo questions selected | 3 questions tested and ready: one single-company, one cross-company, one refusal | ☐ |

**Gate:** All deliverables complete. Demo runs clean. Docs match reality.

---

## 7. Build Priorities

If time runs short, deliver in this order:

**Priority 1 — Must work:**
- Ingestion + metadata (P1)
- Retrieval (P2)
- One-call answer path (P3)
- API endpoint (P5)
- Visible citations

**Priority 2 — Must be believable:**
- Frontend (P7)
- Real eval set with results (P6)
- Real prompt log (P3-6)
- Clean README
- Coherent demo walkthrough

**Priority 3 — Only if time remains:**
- Citation validation (P4)
- Stronger retrieval balancing for multi-company
- Nicer UI
- Architecture diagram
- Roadmap polish

The minimum viable demo: question in → cited answer out → one refusal → eval results exist → docs match reality.
