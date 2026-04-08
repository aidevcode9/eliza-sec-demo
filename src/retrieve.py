"""Retrieve — hybrid search with confidence gating, precomputed BM25 + vectorized cosine."""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field

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
            sub_index = index.get_ticker_subindex(ticker, chunks)
            logger.info("Single-ticker retrieval: %s (%d chunks)", ticker, len(ticker_chunks))
            return _single_retrieve(query, ticker_chunks, top_k, threshold, sub_index)

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
    vector_results = _vector_search(query, chunks, top_k * 2, index, query_embedding=query_embedding)
    bm25_results = _bm25_search(query, chunks, top_k * 2, index)
    fused = _rrf_fuse(vector_results, bm25_results, k=60)

    results = [r for r in fused[:top_k] if r["score"] >= threshold]

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
    per-ticker, then merges and re-ranks by score.
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

        # Use cached per-ticker sub-index
        sub_index = index.get_ticker_subindex(ticker, chunks)

        vector_results = _vector_search(
            query, ticker_chunks, per_ticker_k * 2, sub_index,
            query_embedding=query_embedding,
        )
        bm25_results = _bm25_search(query, ticker_chunks, per_ticker_k * 2, sub_index)
        fused = _rrf_fuse(vector_results, bm25_results, k=60)

        # Take per_ticker_k from this company
        ticker_results = [r for r in fused[:per_ticker_k] if r["score"] >= threshold]
        all_results.extend(ticker_results)

        logger.info(
            "Multi-company: %s yielded %d chunks (from %d candidates)",
            ticker,
            len(ticker_results),
            len(fused),
        )

    # Re-sort merged results by score descending
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]
