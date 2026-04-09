# SEC Filing Intelligence — Phase 1 Engagement Brief

**Prepared by:** Chuck Hernandez  
**Date:** April 10, 2026  
**Client:** Panel simulates a PE firm or investment team  
**Engagement type:** Phase 1 — Proof of Value

---

## 1. Business Problem

Investment professionals spend hours manually reviewing SEC filings to compare companies, track financial trends, and identify risk factors across a portfolio. The provided corpus is large enough to make manual review expensive: 246 filings across 54 companies spanning 2023–2025.

**What the client wants:** Ask a natural-language business question and get a trustworthy, cited answer grounded in SEC filing data.

**Why it matters:** Analyst time is expensive. If the system can reduce the time from “I have a question” to “here is a grounded answer with sources” from hours to seconds, the ROI is immediate.

---

## 2. Trust Bar

SEC filings are regulatory documents. Wrong answers about revenue trends, risk exposure, or business changes can drive bad decisions.

**Design principle:** Every answer cites the specific filing, company, filing date, and section. If the system cannot find sufficient evidence, it refuses rather than guesses.

This is the core trust bar for the proof of value.

---

## 3. Approach — Smallest Trustworthy Solution

This was scoped as a **phase-1 proof of value**, not a full product build. The goal was to demonstrate trustworthy retrieval and answer generation over the client’s data while honoring the single-call runtime constraint.

### What we built

| Component | Decision | Why |
|-----------|----------|-----|
| **Corpus prep** | Strip XBRL / noisy leading text, preserve filing structure | Machine-readable filing noise hurts retrieval quality |
| **Chunking** | Section-based Item chunking with overlap | SEC filings have standard structure; section-aware chunks preserve context |
| **Metadata** | Ticker, filing type, filing date, section name per chunk | Needed for cross-company and time-based answers |
| **Retrieval** | Hybrid search (BM25 + vector) with RRF fusion + Cohere reranker | Lexical catches exact terms, vector catches meaning, reranker rescores for precision |
| **Refusal behavior** | No hard retrieval threshold in demo build; generator refuses when evidence is insufficient | RRF is a ranking signal, not a calibrated confidence score |
| **Generation** | Single LLM call with flat structured output and top-level citations | Meets assignment constraint and produces inspectable answers |
| **Citation validation** | Optional validation on cited quotes | Helps detect citation drift or hallucinated quotes |
| **Evaluation** | Scoped golden set + adversarial set | Proves the demo configuration on representative questions |

### What we intentionally did not build

| Omitted | Why |
|---------|-----|
| Conversational memory | Phase 1 is single-question |
| Authentication / RBAC | Roadmap item, not needed for assessment scope |
| Live corpus sync / connectors | Static corpus for proof of value |
| Multi-step agent workflows | Would violate or complicate the single-call runtime path |
| Fine-tuned model | Off-the-shelf model + strong retrieval is sufficient for Phase 1 |

---

## 4. Evaluation Results

| Metric | Result | Notes |
|--------|--------|-------|
| Golden set | 10/10 (100%) | Core questions including 3 assignment sample questions |
| Adversarial set | 7/7 (100%) | Injection, out-of-scope, speculative, and refusal cases |
| Avg latency (golden) | ~2.5s | Demo configuration |
| Avg latency (adversarial) | ~0.8s | Demo configuration |

**Assessment:** The final demo configuration passes the full evaluation suite: 10 golden questions (single-company, cross-company, temporal, risk/regulatory, and refusal) and 7 adversarial questions (prompt injection, out-of-scope, out-of-corpus, speculative). Earlier broader eval runs exposed weaknesses on exact dollar-amount extraction from deeply nested sections. Those cases were documented and moved to the Phase 2 roadmap rather than being hidden.

### Representative sample results

| Question | Outcome | Notes |
|----------|---------|-------|
| Compare risk factors of Apple and Pfizer | PASS | Cross-company comparison with cited sections |
| What was Uber's total gross bookings for FY2024? | PASS (Refused) | Correct refusal — UBER not in corpus |
| What is the current stock price of NVIDIA? | PASS (Refused) | Correct refusal — not answerable from SEC filings |

---

## 5. Phase 2 Roadmap

If Phase 1 proves the trust bar is met, next steps would be:

- **Conversational context** — support follow-up questions across turns
- **Cross-document temporal analysis** — more robust year-over-year comparisons across multiple filings
- **Hierarchical retrieval** — coarse-to-fine retrieval for deeply nested exact facts
- **Auth / SSO / RBAC** — production access control
- **Scheduled corpus refresh** — batch or connector-driven updates
- **Telemetry / monitoring hardening** — production quality and cost monitoring

**Estimated Phase 2 scope:** 4–6 weeks with a small team.

---

## 6. Panel Walkthrough Plan

### Before opening the laptop
Frame the problem in 60–90 seconds:
- high-trust-bar use case
- static SEC corpus
- one-question-in / one-answer-out
- answer must be grounded or refused

### Demo
Show three queries:
1. a cross-company comparison
2. a single-company business question
3. an out-of-scope / refusal case

### After the demo
Summarize:
- why the architecture is trustworthy
- how the single-call constraint is enforced
- what the eval set covered
- what was intentionally deferred

---

## 7. Key Decisions Summary

| Decision | Reasoning |
|----------|-----------|
| Section-based chunking | Preserves SEC filing semantics better than generic sliding windows |
| Hybrid retrieval | Financial questions benefit from both lexical and semantic recall |
| No hard RRF threshold in demo build | RRF is not a calibrated confidence score |
| Citation-first output | Trust requires inspectable provenance |
| Explicit confidence + refusal on insufficient evidence | Safer than fabricating an answer in a high-trust use case |
| Scoped evaluation | Better to present a truthful demo-scoped eval than overclaim coverage |

---

## 8. Prompt Iteration Summary

| Version | Change | Why | Result |
|---------|--------|-----|--------|
| v1 | Basic answer-from-context prompt | Establish baseline | Weak citation behavior |
| v2 | Structured JSON output | Enforce answer shape | Better answer structure |
| v3 | Filing/date/section citation instructions | Make citations inspectable | Better provenance |
| v4 | Refusal instructions for insufficient evidence | Strengthen fail-closed behavior | Better out-of-scope handling |
| v5 | Cross-company comparison formatting + stronger evidence rules | Improve comparison answers | Stronger comparison structure |
| v6 | Confidence semantics aligned to runtime behavior | Match prompt, backend, and UI | Low-confidence answers are labeled consistently |
| v7 | Flat multi-company output contract | Keep API and UI citations stable | Nested company JSON is prevented and normalized |
