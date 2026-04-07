# Prompt Iteration Log

> Every change to the system prompt, what changed, why, and the result.
> Required deliverable for the Eliza panel presentation.
> Prompt lives in `src/prompts.py` for clean versioning.

---

## Version 1 — Initial scaffold prompt (pre-iteration)

What changed: Initial system prompt in generate.py. Generic RAG prompt with [doc_name, page] citation format.

Why: Scaffold starter kit. This is the baseline before SEC-specific customization.

Result: Not tested. Known issues: references page numbers (corpus is .txt), uses generic doc_name format instead of ticker/filing_type/filing_date/section.

---

## Version 2 — SEC-specific citation schema

What changed: Replaced generic [doc_name, page] citation format with SEC-specific schema: {ticker, filing_type, filing_date, section, doc_name, quoted_text}. Moved prompt to `src/prompts.py` for version tracking. Updated context building in generate.py to pass ticker/filing_type/section_name instead of page number.

Why: Skeptic review identified that generate.py would crash at runtime — `chunk.page` doesn't exist on the new SEC-aware Chunk dataclass. Citation schema must match the metadata available from ingestion (ticker, filing_type, filing_date, section_name). Corpus is .txt files with no page numbers.

Result: Pending — will test in Phase 3.

---
