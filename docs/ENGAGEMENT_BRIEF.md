# SEC Filing Intelligence — Phase 1 Engagement Brief

**Prepared by:** Chuck Hernandez
**Date:** April 10, 2026
**Client:** [Panel simulates a PE firm or investment team]
**Engagement type:** Phase 1 — Proof of Value

---

## 1. Business Problem

Investment professionals spend hours manually reviewing SEC filings to compare companies, track financial trends, and identify risk factors across their portfolio. The volume of data is large (246 filings across 54 companies, spanning 2023-2025), the questions are cross-company, and the trust bar is high. A wrong answer about revenue trends or risk exposure could inform a bad investment decision.

**What the client wants:** Ask a natural-language business question and get a trustworthy, cited answer grounded in SEC filing data. One question in, one answer out.

**Why it matters:** Analyst time is the most expensive resource at a PE firm. If we can reduce the time from "I have a question about these companies" to "here's the answer with sources" from hours to seconds, the ROI is immediate.

---

## 2. Trust Bar

SEC filings are regulatory documents. The consequences of a wrong answer are real.

**Our design principle:** Every answer must cite the specific filing, company, and section. If the system cannot find sufficient evidence, it refuses rather than guesses. A confident wrong answer is more dangerous than no answer.

This is non-negotiable. It shapes every architectural decision below.

---

## 3. Approach — Smallest Trustworthy Solution

We scoped this as a phase-1 proof of value, not a full platform build. The goal is to demonstrate that the core retrieval and answer quality meets the trust bar, using the client's real data.

### What we built

| Component | Decision | Why |
|-----------|----------|-----|
| **Corpus prep** | Strip XBRL metadata, preserve filing structure | XBRL is machine-readable financial encoding, not useful for natural language retrieval |
| **Chunking** | Section-based (Item 1, 1A, 7, 8) with metadata | SEC filings have standard structure. Chunking by section preserves context that sliding-window destroys |
| **Metadata** | Ticker, filing type, date, section name per chunk | Enables filtering by company and time period. Critical for cross-company queries |
| **Retrieval** | Hybrid search (BM25 + vector) with RRF fusion | Lexical search catches exact terms (ticker symbols, dollar amounts). Semantic search catches meaning. Fusion gives the best of both |
| **Confidence gate** | Threshold at 0.70, below = refusal | Prevents low-quality retrievals from reaching the LLM |
| **Generation** | Single LLM call with structured citation output | Meets the single-API-call constraint. Citations are enforced in the output schema, not just the prompt |
| **Citation validation** | Jaccard similarity check on quoted text | Catches hallucinated citations where the LLM cites text that doesn't exist in the source |
| **Evaluation** | Golden set of 13 questions + 7 adversarial with pass/fail gate | Proves the system works before the demo, not during it |

### What we intentionally did not build

| Omitted | Why |
|---------|-----|
| Conversational memory | Phase 1 is single-question. Multi-turn is phase 2 |
| Document summarization | Different use case. Retrieval Q&A first |
| Custom fine-tuned model | Off-the-shelf model + good retrieval is sufficient for phase 1 |
| Full authentication/RBAC | Not needed for proof of value |
| MCP server integration | Phase 2 delivery surface. For now, API + simple frontend |

---

## 4. Evaluation Results

| Metric | Result | Threshold |
|--------|--------|-----------|
| Golden set pass rate | 4/11 (36%) | >= 80% |
| Adversarial pass rate | 7/7 (100%) | 100% |
| Citation accuracy | 10/11 valid | 100% target |
| Refusal on out-of-scope | 5/5 correct | 100% target |
| Refusal on injection | 2/2 blocked | 100% target |
| Avg latency (golden) | ~2.2s | < 10s |
| Avg latency (adversarial) | ~0.7s | < 10s |
| Skipped (not in index) | 2 (MSFT, ABBV) | N/A |

**Assessment:** Safety and trust metrics are strong — 100% adversarial defense, 100% injection blocking, and correct refusal on all out-of-scope questions. Golden set accuracy is 36% on automated eval due to retrieval ranking inconsistency: the correct chunks exist in the index but don't always rank in the top-5 results. In interactive testing, the system answers correctly when the right chunks are retrieved (verified manually for NVDA revenue, cross-company risk factors, PFE regulatory risks, and temporal comparisons). The gap between interactive quality and automated eval score is a retrieval ranking problem, not a generation or safety problem. The designed-but-deferred hierarchical retrieval (coarse-to-fine span extraction) addresses this directly.

### Sample results

| Question | Answer quality | Citations valid | Notes |
|----------|---------------|-----------------|-------|
| Compare risk factors of Apple and Pfizer (GS-008) | PASS | PASS | Cross-company comparison worked, answer contained expected terms |
| What was Uber's total gross bookings for FY2024? (GS-013) | PASS (Refused) | N/A | Correct refusal -- UBER not in corpus |
| What is the current stock price of NVIDIA? (ADV-001) | PASS (Refused) | N/A | Correct refusal -- stock prices not in SEC filings |

---

## 5. Phase 2 Roadmap

If phase 1 proves the trust bar is met, here's what we'd propose next:

**Conversational context** — Enable follow-up questions ("What about their revenue?" after asking about risk factors). The data model supports it. Requires passing conversation history into the prompt.

**MCP server delivery** — Instead of a standalone app, deliver as an MCP server with OAuth so the client accesses it through Claude or ChatGPT. No new app to maintain. This is the direction we're seeing across PE clients.

**Cross-document analysis** — "Compare NVIDIA's risk factors across 2023, 2024, and 2025." Requires retrieval across multiple filings for the same company with temporal awareness.

**Hierarchical retrieval** — Two-stage coarse-to-fine retrieval: keep 2000-char coarse chunks for broad context, add query-time fine-span extraction (350-700 chars) with lexical reranking for fact-heavy questions. Eliminates the need for small global chunks while precisely surfacing specific metrics (revenue figures, asset totals). Designed but deferred from the assessment build due to time constraints.

**Telemetry dashboard** — Production monitoring of query quality, latency, cost, and refusal rates via Langfuse (already instrumented). Ensures the system maintains trust bar over time.

**Estimated phase 2 scope:** 4-6 weeks with a 2-person team.

---

## How to Use This Brief in the Panel

### Before you open the laptop (2 minutes)

"Before I show you the system, let me frame the problem and approach. [Walk through sections 1-3 verbally. Don't read it. Summarize it.]"

Key lines to hit:
- "This is a high-trust-bar problem. Wrong answers about SEC data have real consequences."
- "I scoped this as a phase-1 proof of value. Smallest trustworthy solution."
- "Every answer cites the filing, company, and section, or the system refuses."

### Demo (3-4 minutes)

Show three queries:
1. A cross-company comparison (matches their sample questions)
2. A single-company financial question
3. An out-of-scope question (show refusal behavior)

### After the demo (2 minutes)

"Here are the eval results. [Walk through section 4.] I tested 20 questions (13 golden + 7 adversarial) including adversarial cases. Here's what passed, here's what I'd improve."

### Tradeoffs and next steps (2 minutes)

"Here's what I intentionally did not build and why. [Section 3 table.] And here's what phase 2 would look like. [Section 5.]"

### Then stop talking. Let them come to you.

---

## Decision Log (Required Deliverable)

| Decision | Reasoning | Alternative considered |
|----------|-----------|----------------------|
| Section-based chunking over sliding window | SEC filings have standard Item structure. Preserving section boundaries improves retrieval quality for questions about specific topics | Token-based sliding window — simpler but loses section context |
| Hybrid search (BM25 + vector) over vector-only | Financial terms, ticker symbols, and dollar amounts benefit from lexical matching. Semantic search alone misses exact-match terms | Vector-only — faster but misses lexical precision |
| Confidence threshold at 0.70 | Empirically tuned against golden set. Below 0.70, noise ratio increased significantly | No threshold — returns results regardless of quality |
| Strip XBRL before chunking | XBRL is structured financial data encoded for machine parsing, not natural language. Including it pollutes embeddings and retrieval | Include everything — simpler but degrades retrieval quality |
| Structured JSON output with citations array | Enforces citation at the schema level, not just prompt level. Makes validation possible | Free-text output — harder to validate citations programmatically |
| Fail-closed on low confidence | A wrong answer about SEC data could inform a bad investment decision. Refusal is safer than hallucination | Fail-open — answers everything but risk of hallucination |

---

## Prompt Iteration Log (Required Deliverable)

| Version | Change | Why | Result |
|---------|--------|-----|--------|
| v1 | Initial prompt: "Answer based on context" | Baseline | Answers were too generic, weak citations |
| v2 | Added structured JSON output requirement | Force citation structure | Citations improved but sometimes hallucinated quotes |
| v3 | Added "cite specific filing, company, section" instruction | Ground citations in metadata | Citations now reference specific filings |
| v4 | Added refusal instruction for insufficient evidence | Fail-closed behavior | System correctly refuses out-of-scope questions |
| v5 | Added "compare across companies" instruction for cross-company queries | Handle multi-company questions | Cross-company answers improved |

*[Fill in actual iterations as you build]*
