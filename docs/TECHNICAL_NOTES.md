# Technical Notes — SEC Filing RAG System

> Implementation details for the technical reviewer.
> These notes describe the final demo configuration, not every intermediate experiment recorded in DECISIONS.md.

---

## Pipeline Architecture

```text
Question → Injection Filter → Ticker Detection → Retrieval → Generation → Citation Validation → Response
```

**Single LLM call constraint:** The answer is produced in exactly one `traced_llm_call()`. No query rewriting, no verification loop, no chained calls.

---

## Ingestion (src/ingest.py)

### Text Normalization
SEC filings converted from HTML to `.txt` contain pipe delimiters (`|`) from table cells and unicode replacement characters (`�`). `normalize_text()` replaces these before downstream processing.

### XBRL / Noisy Leading Text Stripping
Each filing starts with a machine-readable or noisy leading block. The ingestion path strips this before section splitting and chunking.

### Section Splitting
SEC Item headers are used as the primary section boundary. The parser also handles cases where Item headers appear mid-line in `.txt` conversions.

### Chunking
Sections are sub-chunked at the demo configuration size with overlap. Each chunk carries metadata including ticker, company, filing type, filing date, and section name.

---

## Retrieval (src/retrieve.py)

### Hybrid Search: BM25 + Vector + RRF
- **BM25:** catches exact terms such as ticker symbols, section names, and financial phrases
- **Vector:** captures semantic similarity
- **RRF:** combines lexical and semantic rankings into one result list

### Ticker-Aware Retrieval
- **Single ticker detected:** restrict retrieval to that company’s chunks
- **Multiple tickers detected:** retrieve per ticker, then merge for balanced coverage

### No Hard RRF Threshold
`CONFIDENCE_THRESHOLD=0.0` in the demo build. RRF is a ranking signal, not a calibrated confidence score, so hard filtering is deferred until broader post-demo evaluation.

---

## Generation (src/generate.py)

### Prompt Behavior
The final prompt instructs the model to:
- answer only from provided context
- cite filing/date/section metadata
- refuse when evidence is insufficient
- keep multi-company answers as plain text inside the top-level `answer` field
- merge all supporting citations into the top-level `citations` array
- resist prompt injection attempts

### Structured Output
The answer is returned as structured JSON with a plain-text `answer` field plus
top-level citations. `generate.py` also normalizes malformed nested company JSON
back into that flat contract so the API and frontend stay consistent.

---

## Citation Validation (src/validate.py)

### Exact Match + Similarity Checks
Validation attempts an exact substring match first, then falls back to token-overlap similarity.

### Validation Metadata
Each citation can include validation metadata such as:
- `valid`
- `validation_note`
- `jaccard_score`

---

## Telemetry (src/telemetry.py)

All model and embedding calls flow through traced wrappers. Optional Langfuse integration can be enabled for production-style latency and cost inspection without changing the core demo behavior.

---

## Known Limitations

| Limitation | Root Cause | Mitigation |
|------------|-----------|------------|
| Some deeply nested exact figures may still be missed | Chunk-level retrieval can still dilute very specific facts | Wider candidate pools + neighbor-aware retrieval reduce misses; hierarchical retrieval remains a Phase 2 roadmap item |
| Single-call design limits self-correction | Assignment constraint | Stronger prompt + retrieval quality compensate |
| Demo corpus path may differ from raw visible repo files | Processed index is the operative runtime dataset | Clarified in README and presentation |

---

## Build Rationale

### Vector Search: numpy (not FAISS, pgvector, Pinecone)
At 75K chunks, brute-force cosine similarity via numpy matrix multiply runs in ~50ms. FAISS adds C++ install complexity for marginal gain at this scale — worth it at 500K+. pgvector requires PostgreSQL infrastructure that a single-user demo doesn't need. Pinecone/Weaviate add managed service dependencies. All are documented as Phase 2 options for production scale.

### RAG Framework: custom (not LlamaIndex, LangChain)
Evaluated LlamaIndex mid-build. Our SEC-specific requirements — section-aware chunking, XBRL stripping, ticker detection, multi-company retrieval — need custom code regardless of framework. At ~2K lines across 8 modules, the custom pipeline is fully debuggable and has no abstraction layers between us and the retrieval logic. Migration risk outweighed framework benefits on a timeboxed build.

### Embedding: text-embedding-3-large (1536 dims)
Best retrieval quality from OpenAI's lineup. Memory footprint (~440MB at 75K chunks) is acceptable for single-user demo. text-embedding-3-small (512 dims, ~150MB) is the Phase 2 option if memory becomes a constraint.

---

## Retrospective

The system passes 100% on our eval suite — 10 golden set questions covering single-company factual, cross-company comparison, temporal, regulatory risk, and refusal scenarios, plus 7 adversarial cases including prompt injection and out-of-scope questions. Safety is the strongest dimension: every out-of-scope or injection attempt is correctly refused.

The architecture is intentionally simple — custom hybrid retrieval over numpy rather than a framework like LlamaIndex or a managed vector DB. At this corpus scale (75K chunks, 54 companies), the simple approach gives us full control and sub-100ms vector search.

If starting over, I'd timebox more time in eval infrastructure — specifically LLM-as-judge evaluation and retrieval regression tests. Time was the primary constraint, and many decisions were made to deliver within the build window rather than optimize. The roadmap covers the improvements we'd make with more time: hierarchical retrieval for deeply nested facts, better citation validation metrics, and production infrastructure.
