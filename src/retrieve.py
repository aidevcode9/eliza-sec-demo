"""Retrieve — hybrid search with confidence gating, precomputed BM25 + vectorized cosine."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from itertools import zip_longest

import numpy as np

from src.config import config
from src.ingest import Chunk, load_chunks
from src.telemetry import traced_embedding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer with punctuation stripping."""
    return [w.strip(".,;:!?()[]{}\"'").lower() for w in text.split() if w.strip()]


# ---------------------------------------------------------------------------
# Multi-company detection
# ---------------------------------------------------------------------------

# Common company short names -> ticker mapping for query matching.
# Populated from loaded chunks at index build time, but supplemented with
# well-known aliases that may not appear in chunk metadata.
_COMPANY_ALIASES: dict[str, str] = {
    "apple": "AAPL",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "pfizer": "PFE",
    "amazon": "AMZN",
    "microsoft": "MSFT",
    "abbvie": "ABBV",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "exxon": "XOM",
    "exxon mobil": "XOM",
    "exxonmobil": "XOM",
}


def detect_query_tickers(
    query: str,
    known_tickers: set[str],
    known_companies: dict[str, str],
) -> list[str]:
    """
    Detect ticker symbols and company names in a query.

    Args:
        query: user question
        known_tickers: set of uppercase ticker strings (e.g. {"AAPL", "NVDA"})
        known_companies: mapping of company name -> ticker (e.g. {"Apple Inc": "AAPL"})

    Returns:
        Deduplicated list of matched tickers, empty if none detected.
    """
    found: set[str] = set()
    query_upper = query.upper()
    query_lower = query.lower()

    # Check explicit tickers (case-sensitive upper match in text)
    # Bug 2 fix: strip punctuation from tokens so "AAPL," matches "AAPL"
    cleaned_tokens = [w.strip(".,;:!?()[]{}\"'") for w in query_upper.split()]
    for ticker in known_tickers:
        if ticker in cleaned_tokens:
            found.add(ticker)

    # Check company names (case-insensitive)
    for name, ticker in known_companies.items():
        if name.lower() in query_lower:
            found.add(ticker)

    # Check common aliases
    for alias, ticker in _COMPANY_ALIASES.items():
        if alias in query_lower and ticker in known_tickers:
            found.add(ticker)

    return sorted(found)


def _requested_filing_types(query: str) -> set[str]:
    """Infer any requested filing types from the query text."""
    query_lower = query.lower()
    requested: set[str] = set()
    if "10-k" in query_lower or "10k" in query_lower:
        requested.add("10-K")
    if "10-q" in query_lower or "10q" in query_lower:
        requested.add("10-Q")
    return requested


def _requests_latest_filing(query: str) -> bool:
    """Return True when the query explicitly asks for the latest filing."""
    query_lower = query.lower()
    return any(phrase in query_lower for phrase in ("most recent", "latest", "newest"))


def _has_explicit_period_reference(query: str) -> bool:
    """Return True when the query names a specific historical period or filing year."""
    return bool(re.search(r"\b20\d{2}\b", query))


def _scope_chunks_for_query(query: str, chunks: list[Chunk]) -> list[Chunk]:
    """Narrow retrieval to the requested filing type or latest filing when explicit."""
    scoped = chunks

    filing_types = _requested_filing_types(query)
    if filing_types:
        type_filtered = [chunk for chunk in scoped if chunk.filing_type.upper() in filing_types]
        if type_filtered:
            scoped = type_filtered

    if _requests_latest_filing(query) and not _has_explicit_period_reference(query):
        dated_chunks = [chunk for chunk in scoped if chunk.filing_date]
        if dated_chunks:
            if len(filing_types) > 1:
                latest_by_type = {
                    filing_type: max(
                        chunk.filing_date
                        for chunk in dated_chunks
                        if chunk.filing_type.upper() == filing_type
                    )
                    for filing_type in filing_types
                    if any(chunk.filing_type.upper() == filing_type for chunk in dated_chunks)
                }
                latest_filtered = [
                    chunk
                    for chunk in dated_chunks
                    if latest_by_type.get(chunk.filing_type.upper()) == chunk.filing_date
                ]
            else:
                latest_date = max(chunk.filing_date for chunk in dated_chunks)
                latest_filtered = [chunk for chunk in dated_chunks if chunk.filing_date == latest_date]
            if latest_filtered:
                scoped = latest_filtered

    return scoped


# ---------------------------------------------------------------------------
# RetrievalIndex — precomputed BM25 + embedding matrix
# ---------------------------------------------------------------------------


@dataclass
class RetrievalIndex:
    """
    Precomputed retrieval index for fast hybrid search.

    Built once from a chunk list. Caches:
    - BM25: tokenized docs, document frequencies, average doc length
    - Vector: numpy matrix of all chunk embeddings
    - Multi-company: known tickers and company names
    """

    chunks: list[Chunk]

    # BM25 precomputed state
    tokenized_docs: list[list[str]] = field(default_factory=list)
    tf_maps: list[Counter] = field(default_factory=list)  # type: ignore[type-arg]
    doc_lengths: list[int] = field(default_factory=list)
    df: Counter = field(default_factory=Counter)  # type: ignore[type-arg]
    avg_dl: float = 0.0

    # Vector precomputed state
    embedding_matrix: np.ndarray | None = None  # (n_chunks, dim)
    embedding_norms: np.ndarray | None = None  # (n_chunks,)
    embedded_chunk_indices: list[int] = field(default_factory=list)

    # Multi-company state
    known_tickers: set[str] = field(default_factory=set)
    known_companies: dict[str, str] = field(default_factory=dict)
    ticker_to_indices: dict[str, list[int]] = field(default_factory=dict)

    # Lazy cache for per-ticker sub-indexes
    _ticker_subindexes: dict[str, "RetrievalIndex"] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Precompute all indices from chunks."""
        self._build_bm25_index()
        self._build_embedding_matrix()
        self._build_company_index()

    def get_ticker_subindex(self, ticker: str, chunks: list[Chunk]) -> "RetrievalIndex":
        """Return cached per-ticker sub-index, building on first access."""
        if ticker not in self._ticker_subindexes:
            indices = self.ticker_to_indices.get(ticker, [])
            ticker_chunks = [chunks[i] for i in indices]
            self._ticker_subindexes[ticker] = RetrievalIndex(ticker_chunks)
        return self._ticker_subindexes[ticker]

    def _build_bm25_index(self) -> None:
        """Tokenize all chunks once, compute df and avg_dl."""
        self.tokenized_docs = []
        self.tf_maps = []
        self.doc_lengths = []
        self.df = Counter()

        for chunk in self.chunks:
            tokens = _tokenize(chunk.text)
            self.tokenized_docs.append(tokens)
            self.tf_maps.append(Counter(tokens))
            self.doc_lengths.append(len(tokens))
            for term in set(tokens):
                self.df[term] += 1

        total_len = sum(self.doc_lengths)
        self.avg_dl = total_len / max(len(self.chunks), 1)

    def _build_embedding_matrix(self) -> None:
        """Stack all chunk embeddings into a numpy matrix for vectorized cosine."""
        embedded = []
        indices = []
        for i, chunk in enumerate(self.chunks):
            if chunk.embedding:
                embedded.append(chunk.embedding)
                indices.append(i)

        if not embedded:
            self.embedding_matrix = None
            self.embedding_norms = None
            self.embedded_chunk_indices = []
            return

        self.embedding_matrix = np.array(embedded, dtype=np.float32)
        self.embedding_norms = np.linalg.norm(self.embedding_matrix, axis=1)
        self.embedded_chunk_indices = indices

    def _build_company_index(self) -> None:
        """Build ticker/company name lookup and per-ticker chunk indices."""
        self.known_tickers = set()
        self.known_companies = {}
        self.ticker_to_indices = {}

        for i, chunk in enumerate(self.chunks):
            ticker = chunk.ticker.upper()
            self.known_tickers.add(ticker)
            if chunk.company:
                self.known_companies[chunk.company] = ticker
            self.ticker_to_indices.setdefault(ticker, []).append(i)


# ---------------------------------------------------------------------------
# Module-level index cache
# ---------------------------------------------------------------------------

_cached_index: RetrievalIndex | None = None


def get_or_build_index(chunks: list[Chunk] | None = None) -> RetrievalIndex:
    """Return cached RetrievalIndex, building it if necessary."""
    global _cached_index
    if _cached_index is not None and chunks is None:
        return _cached_index

    chunks = chunks or load_chunks()
    _cached_index = RetrievalIndex(chunks)
    logger.info(
        "Built RetrievalIndex: %d chunks, %d tickers, embedding_matrix=%s",
        len(chunks),
        len(_cached_index.known_tickers),
        _cached_index.embedding_matrix.shape if _cached_index.embedding_matrix is not None else None,
    )
    return _cached_index


def clear_index_cache() -> None:
    """Clear the cached index (useful for testing)."""
    global _cached_index
    _cached_index = None


# ---------------------------------------------------------------------------
# Vector search (vectorized)
# ---------------------------------------------------------------------------


def _vector_search(
    query: str,
    chunks: list[Chunk],
    top_k: int,
    index: RetrievalIndex | None = None,
    query_embedding: list[float] | None = None,
) -> list[dict]:
    """Cosine similarity search using precomputed embedding matrix."""
    if query_embedding is None:
        query_embedding = traced_embedding([query], label="query_embed")[0]
    query_vec = np.array(query_embedding, dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)

    if query_norm < 1e-10:
        return []

    # Vectorized path: single matmul
    if index is not None and index.embedding_matrix is not None:
        similarities = index.embedding_matrix @ query_vec
        denom = index.embedding_norms * query_norm + 1e-10  # type: ignore[operator]
        similarities = similarities / denom

        # Get top-k indices
        n = min(top_k, len(similarities))
        if n >= len(similarities):
            top_indices = np.argsort(-similarities)
        else:
            top_indices = np.argpartition(-similarities, n)[:n]
            top_indices = top_indices[np.argsort(-similarities[top_indices])]

        return [
            {
                "chunk": chunks[index.embedded_chunk_indices[idx]],
                "score": float(similarities[idx]),
                "method": "vector",
            }
            for idx in top_indices
        ]

    # Fallback: loop (for backwards compat when no index provided)
    scored = []
    for chunk in chunks:
        if not chunk.embedding:
            continue
        chunk_vec = np.array(chunk.embedding, dtype=np.float32)
        similarity = float(
            np.dot(query_vec, chunk_vec)
            / (query_norm * np.linalg.norm(chunk_vec) + 1e-10)
        )
        scored.append({"chunk": chunk, "score": similarity, "method": "vector"})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# BM25 search (precomputed)
# ---------------------------------------------------------------------------


def _bm25_search(
    query: str,
    chunks: list[Chunk],
    top_k: int,
    index: RetrievalIndex | None = None,
) -> list[dict]:
    """BM25 scoring using precomputed index or on-the-fly (fallback)."""
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    k1 = 1.5
    b = 0.75

    # Precomputed path
    if index is not None:
        doc_count = len(chunks)
        scored = []
        for i, chunk in enumerate(chunks):
            tf_map = index.tf_maps[i]
            dl = index.doc_lengths[i]

            score = 0.0
            for qt in query_terms:
                tf = tf_map.get(qt, 0)
                idf = math.log(
                    (doc_count - index.df.get(qt, 0) + 0.5)
                    / (index.df.get(qt, 0) + 0.5)
                    + 1
                )
                tf_score = (tf * (k1 + 1)) / (
                    tf + k1 * (1 - b + b * dl / index.avg_dl)
                )
                score += idf * tf_score

            if score > 0:
                scored.append({"chunk": chunk, "score": score, "method": "bm25"})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # Fallback: compute on-the-fly (backwards compat)
    doc_count = len(chunks)
    df: Counter = Counter()
    all_tokens: list[list[str]] = []
    for chunk in chunks:
        tokens = _tokenize(chunk.text)
        all_tokens.append(tokens)
        for t in set(tokens):
            df[t] += 1

    avg_dl = sum(len(t) for t in all_tokens) / max(doc_count, 1)

    scored = []
    for i, chunk in enumerate(chunks):
        chunk_terms = all_tokens[i]
        dl = len(chunk_terms)
        tf_map: Counter = Counter(chunk_terms)

        score = 0.0
        for qt in query_terms:
            tf = tf_map.get(qt, 0)
            idf = math.log(
                (doc_count - df.get(qt, 0) + 0.5) / (df.get(qt, 0) + 0.5) + 1
            )
            tf_score = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
            score += idf * tf_score

        if score > 0:
            scored.append({"chunk": chunk, "score": score, "method": "bm25"})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------


def _rrf_fuse(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion to combine vector + BM25 results."""
    scores: dict[str, float] = {}
    chunk_map: dict[str, Chunk] = {}

    for rank, r in enumerate(vector_results):
        cid = r["chunk"].chunk_id
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        chunk_map[cid] = r["chunk"]

    for rank, r in enumerate(bm25_results):
        cid = r["chunk"].chunk_id
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        chunk_map[cid] = r["chunk"]

    fused = [
        {"chunk": chunk_map[cid], "score": score, "method": "hybrid"}
        for cid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]
    return fused


# ---------------------------------------------------------------------------
# Candidate pool + neighbor expansion
# ---------------------------------------------------------------------------


def _candidate_pool_size(top_k: int) -> int:
    """Search a wider candidate pool before fusion to avoid early cutoff misses."""
    return max(20, top_k * 5)


def _expand_adjacent_results(
    anchors: list[dict],
    chunks: list[Chunk],
    fused: list[dict],
    max_results: int | None = None,
) -> list[dict]:
    """
    Include immediate same-doc/same-section neighbors around selected hits.

    This preserves local filing context for generation so a retrieved chunk can
    bring along the adjacent answer chunk when the ranking lands one chunk away.
    """
    if not anchors:
        return []

    score_by_id = {r["chunk"].chunk_id: r["score"] for r in fused}
    index_by_id = {chunk.chunk_id: i for i, chunk in enumerate(chunks)}
    expanded: list[dict] = []
    seen: set[str] = set()

    for anchor in anchors:
        anchor_chunk = anchor["chunk"]
        anchor_index = index_by_id.get(anchor_chunk.chunk_id)
        if anchor_index is None:
            continue

        neighbor_indices: list[int] = []
        if anchor_index > 0:
            neighbor_indices.append(anchor_index - 1)
        neighbor_indices.append(anchor_index)
        if anchor_index + 1 < len(chunks):
            neighbor_indices.append(anchor_index + 1)

        for candidate_index in neighbor_indices:
            candidate_chunk = chunks[candidate_index]
            if (
                candidate_chunk.doc_name != anchor_chunk.doc_name
                or candidate_chunk.section_name != anchor_chunk.section_name
            ):
                continue
            if candidate_chunk.chunk_id in seen:
                continue

            seen.add(candidate_chunk.chunk_id)
            if candidate_chunk.chunk_id == anchor_chunk.chunk_id:
                expanded.append(anchor)
            else:
                expanded.append(
                    {
                        "chunk": candidate_chunk,
                        "score": score_by_id.get(candidate_chunk.chunk_id, anchor["score"]),
                        "method": "neighbor",
                    }
                )
            if max_results is not None and len(expanded) >= max_results:
                return expanded

    return expanded


def _finalize_results(
    fused: list[dict],
    chunks: list[Chunk],
    top_k: int,
    threshold: float,
) -> list[dict]:
    """Select top anchors above threshold, then expand with adjacent context."""
    anchors = _select_anchor_results(fused, top_k, threshold)
    return _expand_adjacent_results(anchors, chunks, fused, max_results=top_k * 2)


def _select_anchor_results(
    fused: list[dict],
    top_k: int,
    threshold: float,
) -> list[dict]:
    """Select the top fused results that pass thresholding."""
    return [r for r in fused[:top_k] if r["score"] >= threshold]


# ---------------------------------------------------------------------------
# Top-level retrieve
# ---------------------------------------------------------------------------


def retrieve(
    query: str,
    chunks: list[Chunk] | None = None,
    top_k: int | None = None,
    threshold: float | None = None,
    index: RetrievalIndex | None = None,
) -> list[dict]:
    """
    Hybrid retrieval: vector similarity + BM25, with confidence gate.

    Returns list of {"chunk": Chunk, "score": float, "method": str}
    sorted by score descending. Only results above threshold.

    If multiple companies are detected in the query, retrieves per-ticker
    and merges to ensure balanced cross-company coverage.
    """
    top_k = top_k or config.top_k
    threshold = threshold if threshold is not None else config.confidence_threshold
    if chunks is None:
        chunks = (index.chunks if index else None) or load_chunks()

    if not chunks:
        logger.warning("No chunks available for retrieval")
        return []

    # Build or reuse index
    if index is None:
        index = get_or_build_index(chunks)

    # Multi-company detection
    detected_tickers = detect_query_tickers(
        query, index.known_tickers, index.known_companies
    )

    if len(detected_tickers) >= 2:
        return _multi_company_retrieve(
            query, chunks, top_k, threshold, index, detected_tickers
        )

    if len(detected_tickers) == 1:
        # Single-ticker: filter chunks to that company for focused retrieval
        ticker = detected_tickers[0]
        ticker_indices = index.ticker_to_indices.get(ticker, [])
        if ticker_indices:
            ticker_chunks = [chunks[i] for i in ticker_indices]
            scoped_chunks = _scope_chunks_for_query(query, ticker_chunks)
            if len(scoped_chunks) != len(ticker_chunks):
                sub_index = RetrievalIndex(scoped_chunks)
                logger.info(
                    "Single-ticker retrieval scoped by filing intent: %s (%d -> %d chunks)",
                    ticker,
                    len(ticker_chunks),
                    len(scoped_chunks),
                )
            else:
                sub_index = index.get_ticker_subindex(ticker, chunks)
                logger.info("Single-ticker retrieval: %s (%d chunks)", ticker, len(ticker_chunks))
            return _single_retrieve(query, scoped_chunks, top_k, threshold, sub_index)

    # No ticker detected — global retrieval
    return _single_retrieve(query, chunks, top_k, threshold, index)


def _single_retrieve(
    query: str,
    chunks: list[Chunk],
    top_k: int,
    threshold: float,
    index: RetrievalIndex,
    query_embedding: list[float] | None = None,
) -> list[dict]:
    """Standard global top-k retrieval."""
    if query_embedding is None:
        query_embedding = traced_embedding([query], label="query_embed")[0]
    candidate_pool = _candidate_pool_size(top_k)
    vector_results = _vector_search(
        query, chunks, candidate_pool, index, query_embedding=query_embedding
    )
    bm25_results = _bm25_search(query, chunks, candidate_pool, index)
    fused = _rrf_fuse(vector_results, bm25_results, k=60)
    results = _finalize_results(fused, chunks, top_k, threshold)

    logger.info(
        "Retrieved %d chunks above threshold (%.2f) from %d candidates",
        len(results),
        threshold,
        len(fused),
    )
    return results


def _multi_company_retrieve(
    query: str,
    chunks: list[Chunk],
    top_k: int,
    threshold: float,
    index: RetrievalIndex,
    tickers: list[str],
) -> list[dict]:
    """
    Per-ticker retrieval for cross-company questions.

    Allocates top_k slots evenly across detected tickers, retrieves
    per-ticker, then round-robin interleaves to guarantee balanced coverage.
    """
    # Bug 3 fix: use ceiling division to avoid losing slots
    per_ticker_k = max(2, math.ceil(top_k / len(tickers)))
    all_results: list[dict] = []

    # Embed query once for all tickers
    query_embedding = traced_embedding([query], label="query_embed")[0]

    for ticker in tickers:
        ticker_indices = index.ticker_to_indices.get(ticker, [])
        if not ticker_indices:
            continue

        ticker_chunks = [chunks[i] for i in ticker_indices]
        scoped_chunks = _scope_chunks_for_query(query, ticker_chunks)

        # Use cached per-ticker sub-index unless filing intent narrows the set.
        if len(scoped_chunks) != len(ticker_chunks):
            sub_index = RetrievalIndex(scoped_chunks)
        else:
            sub_index = index.get_ticker_subindex(ticker, chunks)
        candidate_pool = _candidate_pool_size(per_ticker_k)

        vector_results = _vector_search(
            query, scoped_chunks, candidate_pool, sub_index,
            query_embedding=query_embedding,
        )
        bm25_results = _bm25_search(query, scoped_chunks, candidate_pool, sub_index)
        fused = _rrf_fuse(vector_results, bm25_results, k=60)

        # Take per_ticker_k from this company
        ticker_results = _select_anchor_results(fused, per_ticker_k, threshold)
        all_results.extend(ticker_results)

        logger.info(
            "Multi-company: %s yielded %d chunks (from %d candidates)",
            ticker,
            len(ticker_results),
            len(fused),
        )

    # Round-robin interleave to guarantee every ticker is represented
    by_ticker: dict[str, list[dict]] = {}
    for r in all_results:
        t = r["chunk"].ticker
        by_ticker.setdefault(t, []).append(r)
    interleaved: list[dict] = []
    for group in zip_longest(*by_ticker.values()):
        for item in group:
            if item is not None:
                interleaved.append(item)
    final_anchors = interleaved[:top_k]
    return _expand_adjacent_results(
        final_anchors,
        chunks,
        final_anchors,
        max_results=top_k * 2,
    )
