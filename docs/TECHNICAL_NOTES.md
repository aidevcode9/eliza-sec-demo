# Technical Notes — SEC Filing RAG System

> Implementation details for the technical reviewer.
> For design decisions and rationale, see DECISIONS.md.

---

## Pipeline Architecture

```
Question → Injection Filter → Ticker Detection → Retrieval → Generation → Citation Validation → Response
```

**Single LLM call constraint:** The answer is produced in exactly one `traced_llm_call()`. No query rewriting, no verification loop, no chained calls.

---

## Ingestion (src/ingest.py)

### Text Normalization
SEC filings converted from HTML to .txt contain pipe delimiters (`|`) from table cells and unicode replacement characters (`�`). `normalize_text()` replaces these with spaces before any processing, preventing downstream issues with section detection and embedding quality.

### XBRL Stripping
Each filing starts with an XBRL data block (1 to 1800+ lines). Stripped by finding the first line containing "UNITED STATES" — verified present in 100% of corpus files.

### Section Splitting
SEC Item headers appear mid-line in the .txt files (e.g., `35Table of ContentsItem 7. Management's Discussion...`). Pre-normalization inserts newlines before Item headers that follow:
- Digits (page numbers): `35Item 7.`
- "Table of Contents": `Table of ContentsItem 7.`
- Periods (section endings): `applicable.Item 1B.`
- Lowercase letters (concatenated words): `ReservedItem 7.`

TOC lines are filtered by detecting trailing page numbers.

### Chunking
Sections are sub-chunked at 1000 characters with 200-character overlap. Paragraph boundaries are preferred over mid-sentence splits. Each chunk carries metadata: ticker, company, filing_type, filing_date, section_name.

---

## Retrieval (src/retrieve.py)

### Hybrid Search: BM25 + Vector + RRF
- **BM25:** Precomputed at index build time (tokenized docs, document frequencies, avg doc length). Catches exact terms like ticker symbols and dollar amounts.
- **Vector:** Cosine similarity via numpy matrix multiplication against precomputed embedding matrix. Catches semantic meaning.
- **RRF (Reciprocal Rank Fusion):** Combines both ranked lists using `1/(k + rank + 1)` with k=60. A chunk appearing in both lists ranks higher than one in only one.

### Ticker-Aware Retrieval
- Detects ticker symbols and company names in the query
- **Single ticker:** Filters to that company's chunks before searching (reduces noise dramatically)
- **Multi-ticker:** Retrieves per-ticker with ceiling-divided slot allocation, then merges. Ensures cross-company questions get balanced coverage.

### No Hard RRF Threshold
`CONFIDENCE_THRESHOLD=0.0` — RRF scores are not comparable to cosine similarity. Hard filtering would reject good results. Top-k is returned; the generation prompt handles uncertainty via cite-or-refuse.

---

## Generation (src/generate.py, src/prompts.py)

### System Prompt (Version 5)
Key instructions:
- Answer only from provided context
- Cite by ticker, filing type, date, and section
- Refuse if evidence is insufficient (confidence=low)
- Organize multi-company answers by company with comparative summary
- Exact substring quotes only — no paraphrasing
- Temporal comparisons must include both values and the delta
- Injection resistance: refuse if asked to ignore instructions or reveal prompt

### Confidence Calibration
- **High:** Directly and clearly stated in context, multiple supporting quotes
- **Medium:** Supported but requires interpretation, evidence is indirect
- **Low:** Insufficient or ambiguous — flagged with `_warning` in response

### Structured Output
`response_format={"type": "json_object"}` enforces valid JSON. The prompt specifies the exact schema. `setdefault()` ensures all required fields exist even if the LLM omits them.

---

## Citation Validation (src/validate.py)

### Jaccard Similarity
Token-level overlap between the citation's `quoted_text` and retrieved chunk text. Threshold: 0.30 (configurable). Catches cases where the LLM slightly paraphrases the source.

### Substring Match
Checked first — if the exact quote appears verbatim in any retrieved chunk, the citation is valid regardless of Jaccard score.

### Negation Mismatch Detection
Heuristic that flags when the answer and source text disagree on negation words ("not", "cannot", etc.) while sharing significant term overlap. Known to produce false positives on SEC filings (which routinely contain legal negation language). Logged at DEBUG level — informational only, does not affect the response.

### Validation Metadata
Each citation is tagged with: `valid` (bool), `validation_note` (explanation), `jaccard_score` (float). The response carries an overall `citations_valid` boolean.

---

## Telemetry (src/telemetry.py)

### All LLM/Embedding Calls Traced
`traced_llm_call()` and `traced_embedding()` wrap every API call. Tracks: model, tokens in/out, latency (ms), label. Stored in-memory and exposed at `/v1/telemetry`.

### Langfuse Integration
Optional (toggle via `LANGFUSE_ENABLED`). Logs generations and embedding spans to Langfuse cloud for cost tracking and latency monitoring. Uses Langfuse SDK v4 `start_observation()` API. Non-blocking — failures are caught and logged, never crash the pipeline.

---

## Known Limitations

| Limitation | Root Cause | Mitigation |
|------------|-----------|------------|
| Some exact dollar figures not retrieved | 2000→1000 char chunks improved this but deep-nested facts can still miss top-5 | Hierarchical retrieval designed (see DECISIONS.md roadmap) |
| JPM 10-K has most MD&A in Item 15 | JPM filing incorporates by reference | Section splitting captures content; BM25 finds it |
| Negation mismatch false positives | SEC filings use extensive legal negation language | Demoted to DEBUG logging |
| Single LLM call limits self-correction | Assignment constraint | Prompt engineering compensates |
