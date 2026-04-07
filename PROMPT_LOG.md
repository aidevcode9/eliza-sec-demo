# Prompt Iteration Log

> Every change to the system prompt, what changed, why, and the result.
> Required deliverable for the Eliza panel presentation.

---

## Version 1 — Initial scaffold prompt (pre-iteration)

What changed: Initial system prompt in generate.py. Generic RAG prompt with [doc_name, page] citation format.

Why: Scaffold starter kit. This is the baseline before SEC-specific customization.

Result: Not yet tested. Known issues: references page numbers (corpus is .txt), uses generic doc_name format instead of ticker/filing_type/filing_date/section. Will be replaced in Phase 3 with SEC-specific cite-or-refuse prompt.

---
