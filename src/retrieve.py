"""Retrieve — hybrid search with confidence gating."""

import logging
import math
from collections import Counter

import numpy as np

from src.config import config
from src.ingest import Chunk, load_chunks
from src.telemetry import traced_embedding

logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    chunks: list[Chunk] | None = None,
    top_k: int | None = None,
    threshold: float | None = None,
) -> list[dict]:
    """
    Hybrid retrieval: vector similarity + BM25, with confidence gate.

    Returns list of {"chunk": Chunk, "score": float, "method": str}
    sorted by score descending. Only results above threshold.
    """
    top_k = top_k or config.top_k
    threshold = threshold or config.confidence_threshold
    chunks = chunks or load_chunks()

    if not chunks:
        logger.warning("No chunks available for retrieval")
        return []

    # Vector search
    vector_results = _vector_search(query, chunks, top_k * 2)

    # BM25 search
    bm25_results = _bm25_search(query, chunks, top_k * 2)

    # Reciprocal Rank Fusion
    fused = _rrf_fuse(vector_results, bm25_results, k=60)

    # Confidence gate
    results = [r for r in fused[:top_k] if r["score"] >= threshold]

    logger.info(
        f"Retrieved {len(results)} chunks above threshold "
        f"({threshold}) from {len(fused)} candidates"
    )
    return results


def _vector_search(query: str, chunks: list[Chunk], top_k: int) -> list[dict]:
    """Cosine similarity search."""
    query_embedding = traced_embedding([query], label="query_embed")[0]
    query_vec = np.array(query_embedding)

    scored = []
    for chunk in chunks:
        if not chunk.embedding:
            continue
        chunk_vec = np.array(chunk.embedding)
        similarity = float(np.dot(query_vec, chunk_vec) / (
            np.linalg.norm(query_vec) * np.linalg.norm(chunk_vec) + 1e-10
        ))
        scored.append({"chunk": chunk, "score": similarity, "method": "vector"})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _bm25_search(query: str, chunks: list[Chunk], top_k: int) -> list[dict]:
    """Simple BM25 scoring."""
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    # Document frequencies
    doc_count = len(chunks)
    df: Counter = Counter()
    for chunk in chunks:
        terms = set(_tokenize(chunk.text))
        for t in terms:
            df[t] += 1

    # BM25 parameters
    k1 = 1.5
    b = 0.75
    avg_dl = sum(len(_tokenize(c.text)) for c in chunks) / max(doc_count, 1)

    scored = []
    for chunk in chunks:
        chunk_terms = _tokenize(chunk.text)
        dl = len(chunk_terms)
        tf_map: Counter = Counter(chunk_terms)

        score = 0.0
        for qt in query_terms:
            tf = tf_map.get(qt, 0)
            idf = math.log((doc_count - df.get(qt, 0) + 0.5) / (df.get(qt, 0) + 0.5) + 1)
            tf_score = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
            score += idf * tf_score

        if score > 0:
            scored.append({"chunk": chunk, "score": score, "method": "bm25"})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


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


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer."""
    return [w.strip(".,;:!?()[]{}\"'").lower() for w in text.split() if w.strip()]
