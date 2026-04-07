RESEARCH BRIEF
==============

> Produced by researcher agent. Verified against 5 representative files:
> NVDA_10K_2025-02-26, JPM_10Q_2025Q1_2025-05-01, PFE_10K_2022Q4_2023-02-23,
> TSLA_10K_2026-01-29, TSLA_10K_2022Q4_2023-01-31
>
> Input for coder agent. All claims below are verified by reading actual files.

---

## Corpus summary

247 items in `data/`: 246 SEC filing .txt files (89 10-K annual reports, 157 10-Q quarterly reports) from 54 US public companies, plus 1 `manifest.json` metadata file. Coverage spans filing dates from 2022 to 2026. Total raw corpus size: ~82M characters (~79M after XBRL stripping). 15 companies have full quarterly coverage for 2023-2025. Sectors represented: technology (NVDA, AAPL, MSFT, META, GOOG, AMZN, ADBE, AMD, CSCO, CRM, INTC, ORCL, IBM, NFLX), financial services (JPM, GS, MS, BAC, BLK, AXP, MA, V), healthcare (PFE, JNJ, MRK, LLY, ABBV, UNH, TMO), consumer (TSLA, NKE, SBUX, MCD, KO, PEP, PG, COST, HD, TGT, WMT, DIS), energy (XOM, CVX), industrial (BA, CAT, DE, GE, LMT, RTX, UPS), and telecom (T, VZ, CMCSA, BRK).

## Document types

Plain text (.txt) only. No PDFs, no DOCX, no scanned documents. Each file is a single SEC filing converted from HTML/XBRL to plain text. All files are machine-readable with consistent encoding.

## Structure

**Consistent across all 246 files, verified on 5 diverse samples:**

1. **Metadata header** — Key-value pairs, one per line. Two variants:
   - **Older pattern (192 files, 78%):** 8 fields — Company, Ticker, Filing Type, Filing Date, Report Period, Quarter, CIK, Source, URL
   - **Newer pattern (54 files, 22%):** 6 fields — Company, Ticker, Filing Type, Filing Date, CIK, Source, URL (no Report Period or Quarter)
   - Parsing approach: read key-value pairs until the separator line. Do NOT assume a fixed line count.

2. **Separator line:** `============================================================` (60 equals signs). Present in 100% of files. Reliable boundary marker.

3. **XBRL data block:** Dense machine-readable XBRL tags on one or more lines. Varies wildly in length (1 line to 1800+ lines). Contains no useful filing content. Must be stripped.

4. **Filing content:** Starts at the line containing `UNITED STATES` (specifically "UNITED STATES SECURITIES AND EXCHANGE COMMISSION"). Verified present in 100% of sampled files. This is the reliable XBRL-end / content-start boundary.

5. **SEC structure within filing content:**
   - Table of Contents (with page references, pipe-delimited in most files)
   - Part I / Part II / Part III / Part IV headers
   - Item sections within each Part

**10-K Item structure (verified on NVDA, PFE, TSLA):**
| Item | Title | Typical content |
|------|-------|-----------------|
| Item 1 | Business | Company overview, products, strategy |
| Item 1A | Risk Factors | Key risks — often the longest section (10K+ chars) |
| Item 1B | Unresolved Staff Comments | Usually brief or N/A |
| Item 1C | Cybersecurity | Post-2023 filings only |
| Item 2 | Properties | Facilities and locations |
| Item 3 | Legal Proceedings | Pending litigation |
| Item 4 | Mine Safety Disclosures | Usually N/A |
| Item 5 | Market for Common Equity | Stock info, buybacks |
| Item 6 | [Reserved] | Placeholder in recent filings |
| Item 7 | MD&A | Financial discussion — high-value for Q&A |
| Item 7A | Market Risk Disclosures | Quantitative risk metrics |
| Item 8 | Financial Statements | Tables + notes — very large |
| Items 9-9C | Controls, Other Info | Accounting, procedures |
| Items 10-14 | Governance | Directors, compensation (often by reference) |
| Item 15 | Exhibits | Exhibit index + financial statement schedules |
| Item 16 | Form 10-K Summary | Usually brief |

**10-Q Item structure (verified on JPM):**
- Part I: Item 1 (Financial Statements), Item 2 (MD&A), Item 3 (Market Risk), Item 4 (Controls)
- Part II: Item 1 (Legal), Item 1A (Risk Factors), Item 2 (Unregistered Sales), Item 3 (Defaults), Item 4 (Mine Safety), Item 5 (Other Info), Item 6 (Exhibits)

**Header formatting varies across filers:**
- NVDA uses mixed case: `Item 1A. | Risk Factors`
- PFE uses ALL CAPS: `ITEM 1A. RISK FACTORS`
- Pipe separators appear in Table of Contents lines but not in body section headers
- Body section headers appear at line start, e.g., `Item 7. Management's Discussion...`
- Cross-references appear mid-line: `...see Item 1A. Risk Factors...`
- **Regex must be case-insensitive and anchor to line start** to distinguish section boundaries from cross-references

## Recommended chunking

**Primary strategy: Section-aware chunking by SEC Item boundaries.**

Each Item section becomes one or more chunks carrying full metadata (ticker, filing_type, filing_date, section_name).

**Implementation approach:**
1. Parse metadata header (read until separator line `====...`)
2. Skip XBRL block (skip until line containing "UNITED STATES")
3. Split filing content on Item header regex: `^(Item|ITEM)\s+\d+[A-C]?\.?\s`
4. Each section gets metadata: `{ticker, filing_type, filing_date, section_name, chunk_index}`
5. Sections exceeding `CHUNK_SIZE` (2000 chars) get sliding-window sub-chunking with `CHUNK_OVERLAP` (200 chars)

**Why this strategy:**
- Section-level chunks preserve semantic coherence (a risk factor stays together)
- Enables precise section-level citations ("NVDA 10-K 2025-02-26, Item 1A")
- Sub-chunking handles large sections (Item 1A Risk Factors, Item 8 Financial Statements) without losing context
- Estimated ~44K chunks at 2000-char target

**Edge cases to handle:**
- Table of Contents lines match Item regex but should be skipped (they contain pipe `|` characters and page numbers)
- Some Items are just references to proxy ("Information required...is incorporated by reference")
- Item 1C (Cybersecurity) only exists in post-2023 10-K filings
- 10-Q Part headers (`Part I`, `Part II`) need to be recognized to namespace Items correctly (10-Q has two "Item 1" sections)

## Metadata available

**From file header (structured, always present):**
- Company name (e.g., "NVIDIA Corporation")
- Ticker symbol (e.g., "NVDA")
- Filing type with description (e.g., "10-K (Annual Report)")
- Filing date (e.g., "2025-02-26")
- CIK number
- SEC EDGAR source URL
- Report period (older files only, e.g., "2024-01-28")
- Quarter (older files only, e.g., "2024Q1")

**From filename (parseable):**
- Two patterns to handle:
  - `{TICKER}_{TYPE}_{YYYYQn}_{DATE}_full.txt` — 192 files (78%)
  - `{TICKER}_{TYPE}_{DATE}_full.txt` — 54 files (22%)
- Recommended: parse metadata from file header, not filename (header is more reliable and complete)

**From `manifest.json`:**
- Corpus-level metadata, sector classifications, file list

**NOT available:**
- Page numbers (corpus is .txt, not PDF)
- Paragraph-level identifiers
- XBRL-tagged financial data in structured form (raw XBRL is present but not useful for text RAG)

## Risks

1. **XBRL block size is unpredictable.** Ranges from 1 line to 1800+ lines. Boundary detection MUST use content matching ("UNITED STATES"), not line-number offsets. Using a fixed skip count will break on long-XBRL files.

2. **Item header false positives.** In-text cross-references like "see Item 1A" or "described in Item 7" look like section boundaries. The regex must anchor to line start (`^`) and may need to exclude lines containing "see " or "described in" prefixes. Table of Contents lines also match; filter those by detecting pipe characters or page-number patterns.

3. **10-K vs 10-Q structural differences.** 10-Q has a different Item numbering scheme (Part I/Part II with different Items). The chunking logic must detect filing type from metadata and apply the correct section map. Both 10-K and 10-Q have an "Item 1" but they mean completely different things.

4. **Very large sections.** Item 1A (Risk Factors) regularly exceeds 10,000 characters. Item 8 (Financial Statements) can be 100K+ characters with dense tables. Sub-chunking with overlap is mandatory for these.

5. **Financial tables in plain text.** Tables lose formatting in .txt conversion. Column alignment is gone. Numbers may be ambiguous without headers. The LLM may misinterpret tabular data. Consider this a retrieval quality risk.

6. **No page numbers for citation.** Citations must use the pattern: `{ticker} {filing_type} {filing_date}, {section_name}`. This is less precise than page-level citation but is the best available given .txt format.

7. **Proxy-reference Items.** Some Items (especially 10-14 in 10-K) just say "incorporated by reference to proxy statement." These are nearly empty and should be chunked but will produce refusals on questions about their content. This is correct behavior.

8. **Newer files lack Quarter/Report Period in header.** The 54 newer-pattern files omit these fields. If quarter is needed, it must be inferred from filing date or filename. The header parser must not crash on missing fields.

## Recommended first slice

Start with 10-K filings from the 6 eval-priority companies: **NVDA, AAPL, TSLA, JPM, PFE, AMZN**. These are the companies referenced in the sample evaluation questions and golden set. This gives ~20 10-K files to validate chunking, embedding, and retrieval before scaling to the full 246-file corpus. Expand to full corpus only after confirming:
- Section boundary detection works on all 6 companies
- Metadata extraction handles both header patterns
- XBRL stripping works on varying block sizes
- Retrieval returns correct sections for golden set questions

## Golden set candidates

These questions can be answered from the verified corpus and span different filing types, companies, and section types:

1. **"What are NVIDIA's primary risk factors related to export controls?"** — NVDA 10-K, Item 1A. Verified: detailed export control discussion present in MD&A and Risk Factors.

2. **"What was NVIDIA's total revenue for fiscal year 2025?"** — NVDA 10-K 2025-02-26, Item 7 (MD&A). Single-company factual retrieval.

3. **"What are the primary risk factors facing Apple, Tesla, and JPMorgan, and how do they compare?"** — Multi-company cross-reference, Item 1A across 3 filings. Tests multi-document retrieval.

4. **"How has Pfizer's revenue changed from 2020 to 2022?"** — PFE 10-K 2022Q4, Item 7 (MD&A). Temporal comparison within one filing.

5. **"What regulatory risks do JPMorgan Chase face?"** — JPM 10-K or 10-Q, Item 1A or Part II Item 1A. Tests financial-sector specific content.

6. **"What is Tesla's manufacturing capacity and factory locations?"** — TSLA 10-K, Items 1 and 2. Tests Business + Properties sections.

7. **Out-of-scope test: "What is the current stock price of NVIDIA?"** — Should produce a refusal (not in filings).

---

## Summary for coder agent

**To implement ingestion (`src/ingest.py`), you need:**
1. A metadata parser that reads key-value pairs until the `====` separator (handle both 6-field and 8-field headers)
2. An XBRL stripper that finds the first line containing "UNITED STATES" and discards everything before it
3. A section splitter using case-insensitive regex anchored at line start: `^(Item|ITEM)\s+\d+[A-C]?\.?\s` — with logic to skip Table of Contents matches and cross-references
4. 10-K vs 10-Q awareness: detect filing type from metadata, apply correct section map
5. Sub-chunking for sections exceeding 2000 chars (sliding window, 200 char overlap)
6. Each chunk must carry: `{ticker, company, filing_type, filing_date, section_name, chunk_index, source_file}`

**IMPORTANT — Scaffold replacement notice:**
The existing `src/ingest.py` and `src/generate.py` are generic RAG scaffold code. They use page-based citations, generic sliding-window chunking, and PDF loading — none of which apply to this SEC corpus. The `Chunk` dataclass is missing `ticker`, `filing_type`, `filing_date`, and `section_name` fields. The system prompt in `generate.py` references `[doc_name, page]` format which doesn't work for .txt filings. **These files must be REPLACED with SEC-specific logic, not extended.** Build from the research brief requirements, not from the scaffold patterns.
