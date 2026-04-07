# Design Decisions Log

> Timestamped record of every architectural and design choice.
> Required deliverable for the Eliza panel presentation.

---

## 2026-04-07 14:00 — Corpus Structure Analysis

Decision: Corpus is 246 .txt files (89 10-K, 157 10-Q) from 54 companies. Each file has an 8-line metadata header, separator line, XBRL data block, then actual filing content.

Reasoning: Need to understand file format before building ingestion. Manual inspection of 6+ files across different companies and filing types confirmed consistent structure.

Alternative considered: Treating files as unstructured text without parsing metadata header — rejected because header provides reliable structured metadata (ticker, filing type, date, quarter).

Risk: None — this is observational.

---

## 2026-04-07 14:05 — XBRL Boundary Detection

Decision: Use "UNITED STATES" as the primary boundary marker to strip XBRL data. This pattern appears in 100% of files (verified all 246). XBRL block sits between the separator line and this marker.

Reasoning: Tested across all files. The line containing "UNITED STATES" (start of SEC header) reliably marks where filing content begins. XBRL block size varies (line 11 in most files, line 1857 in MSFT_10K_2022) but the marker is always present.

Alternative considered: "Table of Contents" as boundary — appears in some files but only as a secondary marker within the filing, not as the XBRL boundary. Using line-number heuristics — rejected as fragile given variable XBRL sizes.

Risk: If a future filing omits the SEC header entirely. Mitigation: fallback to "Table of Contents" or first "Item" heading.

---

## 2026-04-07 14:10 — Filename Metadata Patterns

Decision: Support two filename patterns: `TICKER_TYPE_YYYYQn_DATE_full.txt` (78%, 192 files) and `TICKER_TYPE_DATE_full.txt` (22%, 54 files). Parse both in ingest.py.

Reasoning: Newer filings omit the quarter field. Both patterns reliably provide ticker, filing type, and date. Quarter can be inferred from the metadata header when missing from filename.

Alternative considered: Only parsing from metadata header — rejected because filename is a useful cross-check and the header is more expensive to read.

Risk: Future filename format changes. Low risk for static corpus.

---

## 2026-04-07 14:15 — SEC Section Header Mapping

Decision: Chunk by Item headers (Item 1, Item 1A, Item 7, etc.) as primary section boundaries. 10-K and 10-Q have different Item structures.

Reasoning: 10-K has Items 1-16 (Business, Risk Factors, MD&A, Financials, etc.). 10-Q has Items 1-6 in Part I (Financial Info) and Part II (Other Info). Item headers appear consistently but some in-text cross-references ("see Item 1A") can create false matches — anchor on Item appearing at/near line start.

Alternative considered: Paragraph-based chunking only — rejected because section-aware chunks preserve semantic context and enable section-level citation.

Risk: Inconsistent header formatting across filers. Some use "ITEM 1A." (caps), others "Item 1A." (mixed case). Regex must be case-insensitive.

---

## 2026-04-07 14:20 — Corpus Size Estimation

Decision: Expect ~44,000 chunks at 2000 chars with 200 overlap. Total corpus is ~79M chars after stripping headers/XBRL. Average file is ~322K chars stripped.

Reasoning: Measured across all 246 files. This chunk count is manageable for embedding and vector search. No need for tiered storage or sampling.

Alternative considered: Larger chunk sizes (4000 chars) to reduce count — may revisit if retrieval quality suffers, but 2000 chars keeps chunks focused.

Risk: Large sections (Item 1A Risk Factors can be 10K+ chars) will produce many sub-chunks. Metadata preservation on sub-chunks is critical.

---

## 2026-04-07 14:25 — Evaluation Set Design

Decision: 10 golden set questions + 7 adversarial questions. Categories cover: single-company factual (4), cross-company comparison (1), temporal comparison (2), risk factors (2), refusal/adversarial (7).

Reasoning: Questions are grounded in verified facts from actual filings (NVDA, AAPL, TSLA, JPM, PFE, AMZN). Each golden question has exact expected values and source citations. Adversarial set covers out-of-scope, injection, out-of-corpus, speculative, and scope-overflow.

Alternative considered: 15+ questions — rejected per REQUIREMENTS.md guidance (4-hour build, quality over quantity). Also considered synthetic questions — rejected because real corpus-grounded questions are more trustworthy for eval.

Risk: Small eval set may miss failure modes. Mitigation: adversarial set specifically targets known RAG weaknesses.

---
