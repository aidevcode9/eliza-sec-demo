# REQUIREMENTS.md - SEC Filing RAG Assessment

> Lean build driver for the Eliza FDE panel assessment.
> Acceptance criteria are used to keep the repo aligned to demo readiness and deliverables.

---

## 1. Goal

Build a lightweight retrieval-augmented QA demo over the provided SEC filings corpus.

The system must:
- accept a natural-language business question
- retrieve relevant filing evidence from the provided corpus
- produce the final answer in **one LLM API call**
- return a structured, evidence-grounded answer with visible citations
- be usable through a simple front-end demo

This is a demo-first assessment build, not a production platform.

---

## 2. Scope

### In scope
- Offline ingestion of the provided SEC corpus (246 `.txt` filings)
- Parsing filing text and metadata (ticker, filing type, date, section)
- Chunking filings into retrievable units (section-aware)
- Building a retrieval index (hybrid: BM25 + vector)
- Retrieving context for a user question
- Packing context into one final answer prompt
- One final LLM call for answer generation
- Returning structured answer + citations
- Simple Streamlit front-end for live demo
- Real evaluation set and quality notes
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

These belong in the Phase 2 roadmap discussion, not the assessment build.

---

## 3. Key Assumptions

- The provided corpus is the source of truth and is static for the build.
- Authentication is a roadmap item confirmed with David.
- Data update paths may be discussed but are not implemented.
- The runtime answer path must use exactly one LLM API request.
- Indexing, chunking, and retrieval preparation run before the answer call.
- A lightweight single-user Streamlit UI is sufficient.
- The corpus is `.txt` files, not PDFs. There are no page numbers. Cite by filing, section, and date.

---

## 4. Success Criteria

The build is successful if it can:

1. Answer at least one live business question end-to-end in the UI.
2. Use retrieved filing evidence in a single final LLM call.
3. Cite source filings clearly: ticker, filing type, filing date, section, and supporting quote.
4. Handle at least:
   - one single-company factual question
   - one multi-company comparison question
   - one time-based comparison question
   - one insufficient-evidence / refusal case
5. Be explained clearly in a client-style walkthrough under 12 minutes.

---

## 5. Top Risks

| Risk | Mitigation |
|------|------------|
| Noisy SEC text reduces retrieval quality | Strip XBRL / noisy leading text before chunking |
| Missing or incorrect metadata weakens comparison questions | Parse from both file header and filename; cross-check |
| Retrieval over-focuses on one company | Test multi-company retrieval early; use ticker-aware retrieval |
| RRF fusion scores are not calibrated confidence values | Do **not** hard-filter on RRF scores in the demo build |
| Citation format unclear for text-based filings | Cite by ticker, filing type, filing date, and section |
| Docs overstate what the code does | Keep docs aligned to the final demo configuration |
| Extra complexity violates single-call constraint | No query rewrite, no verification loop, no chained LLM calls |
| Demo fails on live question | Rehearse with 3 pre-tested questions and have backups |

---

## 6. Build Checklist

### Phase 0 - Corpus Analysis
- [x] Read 5+ filings across different companies and filing types
- [x] Document XBRL/noisy-text boundary
- [x] Map Item header patterns for 10-K and 10-Q
- [x] Confirm filename metadata patterns
- [x] Estimate corpus size and chunking implications
- [x] Write evaluation set covering factual, cross-company, temporal, risk, refusal, and adversarial cases

**Checkpoint:** Corpus structure and evaluation set are documented in `DECISIONS.md` and `evals/`.

### Phase 1 - Ingestion Pipeline
- [x] Load all provided `.txt` files from `data/`
- [x] Strip noisy leading text
- [x] Chunk by SEC Item boundaries when possible
- [x] Sub-chunk large sections with overlap
- [x] Preserve metadata on every chunk
- [x] Generate embeddings
- [x] Persist chunks + embeddings for reload
- [x] `uv run python -m src.ingest` completes successfully

**Checkpoint:** Spot-check chunks for at least 3 companies. Metadata and section names look correct.

### Phase 2 - Retrieval
- [x] Vector search works
- [x] BM25 search works
- [x] Hybrid fusion (RRF) works
- [x] Top-k retrieval returns results without brittle hard thresholds
- [x] Multi-company retrieval does not collapse to one company on the supported demo questions
- [x] Retrieval results carry citation metadata
- [x] Spot-check retrieval against golden questions

**Checkpoint:** For golden questions, the correct filings appear in the retrieved result set.

### Phase 3 - Generation (Single LLM Call)
- [x] Prompt answers from context only
- [x] Output is structured JSON
- [x] Insufficient evidence triggers refusal; weak evidence may still return a low-confidence answer with a warning
- [x] Cross-company questions are organized cleanly
- [x] Final answer comes from exactly one `traced_llm_call()`
- [x] Prompt iterations are logged in `PROMPT_LOG.md`
- [x] Injection attempts are refused

**Checkpoint:** Review 3 answers. Citations are specific and verifiable.

### Phase 4 - Citation Validation (if time permits)
- [x] Exact substring validation attempted first
- [x] Jaccard similarity check available
- [x] Citations tagged with validation metadata
- [x] Overall `citations_valid` flag included

**Note:** Priority 3. Ship ingestion, retrieval, generation, API, evals, and frontend first.

### Phase 5 - Pipeline + API
- [x] End-to-end pipeline runs
- [x] `POST /v1/ask` returns structured answer JSON
- [x] `GET /healthz` returns service status
- [x] Example request in README works

**Checkpoint:** Run the example request and get a cited answer.

### Phase 6 - Evaluation
- [x] Eval runner executes the scoped golden + adversarial sets
- [x] Coverage includes factual, cross-company, temporal, risk/regulatory, refusal, and adversarial cases
- [x] Results and known failure modes are documented honestly
- [x] `ENGAGEMENT_BRIEF.md` reflects the final demo-scoped eval story

**Checkpoint:** Evaluation notes are truthful, reproducible, and easy to explain.

### Phase 7 - Frontend
- [x] Streamlit app accepts a question
- [x] Answer is displayed clearly
- [x] Citations are human-readable
- [x] Refusal reason is shown clearly
- [x] Loading state exists
- [x] One pre-tested demo question is easy to run

**Checkpoint:** Ask a question in the UI and inspect the answer and citations.

### Phase 8 - Polish + Presentation
- [x] `DECISIONS.md` matches what was actually built
- [x] `PROMPT_LOG.md` matches current prompt behavior
- [x] `ENGAGEMENT_BRIEF.md` contains final demo-ready numbers and wording
- [x] `README.md` is accurate and does not overclaim
- [x] Lint passes
- [ ] Demo path is rehearsed
- [ ] 3 demo questions are selected (single-company, cross-company, refusal)

**Checkpoint:** The demo runs cleanly and the docs match reality.

---

## 7. Build Priorities

### Priority 1 - Must work
- Ingestion + metadata
- Retrieval
- One-call answer path
- API endpoint
- Visible citations

### Priority 2 - Must be believable
- Frontend
- Real eval set with results
- Real prompt log
- Clean README
- Coherent demo walkthrough

### Priority 3 - Only if time remains
- Stronger citation validation
- Additional telemetry polish
- Extra UI polish
- Roadmap refinement
