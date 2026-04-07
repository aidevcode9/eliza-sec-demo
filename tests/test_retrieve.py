"""Tests for retrieval — BM25, vector search, RRF fusion, multi-company detection."""

from unittest.mock import patch

import numpy as np
from src.ingest import Chunk
from src.retrieve import (
    RetrievalIndex,
    _bm25_search,
    _rrf_fuse,
    _tokenize,
    _vector_search,
    detect_query_tickers,
    retrieve,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    chunk_id: str,
    text: str,
    ticker: str = "TEST",
    company: str = "Test Corp",
    embedding: list[float] | None = None,
) -> Chunk:
    """Build a minimal Chunk for testing."""
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        doc_name=f"{ticker}_10K_2025-01-01_full.txt",
        ticker=ticker,
        company=company,
        filing_type="10-K",
        filing_date="2025-01-01",
        section_name="Item 1",
        embedding=embedding or [],
    )


# ---------------------------------------------------------------------------
# BM25 tests
# ---------------------------------------------------------------------------


class TestBM25:
    """BM25 scoring correctness."""

    def test_bm25_scores_relevant_higher(self) -> None:
        """A chunk containing query terms should score higher than one without."""
        relevant = _make_chunk("c1", "NVIDIA revenue grew significantly in fiscal year 2025")
        irrelevant = _make_chunk("c2", "The weather today is sunny and warm outside")
        chunks = [relevant, irrelevant]

        results = _bm25_search("NVIDIA revenue", chunks, top_k=5)
        assert len(results) >= 1
        assert results[0]["chunk"].chunk_id == "c1"

    def test_bm25_returns_empty_for_no_match(self) -> None:
        """Query with zero term overlap should return nothing."""
        chunk = _make_chunk("c1", "Apple designs consumer electronics products")
        results = _bm25_search("xyzzyplugh", [chunk], top_k=5)
        assert results == []


# ---------------------------------------------------------------------------
# RRF fusion tests
# ---------------------------------------------------------------------------


class TestRRFFuse:
    """Reciprocal Rank Fusion combining vector + BM25 rankings."""

    def test_rrf_fuse_combines_rankings(self) -> None:
        """A chunk appearing in both lists should rank higher than one in only one."""
        c1 = _make_chunk("c1", "shared result")
        c2 = _make_chunk("c2", "vector only")
        c3 = _make_chunk("c3", "bm25 only")

        vector_results = [
            {"chunk": c1, "score": 0.9, "method": "vector"},
            {"chunk": c2, "score": 0.8, "method": "vector"},
        ]
        bm25_results = [
            {"chunk": c1, "score": 5.0, "method": "bm25"},
            {"chunk": c3, "score": 4.0, "method": "bm25"},
        ]

        fused = _rrf_fuse(vector_results, bm25_results, k=60)
        # c1 appears in both lists so should have highest fused score
        assert fused[0]["chunk"].chunk_id == "c1"

    def test_rrf_fuse_handles_disjoint_lists(self) -> None:
        """Chunks appearing in only one list still appear in fusion."""
        c1 = _make_chunk("c1", "vector only")
        c2 = _make_chunk("c2", "bm25 only")

        vector_results = [{"chunk": c1, "score": 0.9, "method": "vector"}]
        bm25_results = [{"chunk": c2, "score": 5.0, "method": "bm25"}]

        fused = _rrf_fuse(vector_results, bm25_results, k=60)
        ids = {r["chunk"].chunk_id for r in fused}
        assert ids == {"c1", "c2"}

    def test_rrf_fuse_respects_top_k(self) -> None:
        """_rrf_fuse returns all fused results (top_k applied by caller)."""
        chunks = [_make_chunk(f"c{i}", f"text {i}") for i in range(10)]
        vector_results = [
            {"chunk": c, "score": 1.0 - i * 0.1, "method": "vector"}
            for i, c in enumerate(chunks)
        ]
        bm25_results = [
            {"chunk": c, "score": 10.0 - i, "method": "bm25"}
            for i, c in enumerate(chunks)
        ]

        fused = _rrf_fuse(vector_results, bm25_results, k=60)
        assert len(fused) == 10


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


class TestTokenize:
    """Basic tokenization."""

    def test_tokenize_lowercases_and_splits(self) -> None:
        """'NVIDIA Revenue 10-K' should produce ['nvidia', 'revenue', '10-k']."""
        tokens = _tokenize("NVIDIA Revenue 10-K")
        assert tokens == ["nvidia", "revenue", "10-k"]
        # All tokens are lowercase
        assert all(t == t.lower() for t in tokens)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestRetrieveEdgeCases:
    """Edge cases for the top-level retrieve function."""

    def test_retrieve_empty_chunks_returns_empty(self) -> None:
        """Passing an empty chunk list should return [] gracefully."""
        results = retrieve("any query", chunks=[])
        assert results == []


# ---------------------------------------------------------------------------
# Multi-company detection
# ---------------------------------------------------------------------------


class TestDetectQueryTickers:
    """Ticker and company name detection in queries."""

    def test_detects_ticker_in_query(self) -> None:
        known_tickers = {"AAPL", "NVDA", "TSLA"}
        known_companies = {"Apple Inc": "AAPL", "NVIDIA Corporation": "NVDA", "Tesla Inc": "TSLA"}
        result = detect_query_tickers("What are Apple and NVIDIA risk factors?", known_tickers, known_companies)
        assert "AAPL" in result
        assert "NVDA" in result

    def test_detects_single_ticker(self) -> None:
        known_tickers = {"AAPL", "NVDA"}
        known_companies = {"Apple Inc": "AAPL", "NVIDIA Corporation": "NVDA"}
        result = detect_query_tickers("Tell me about AAPL revenue", known_tickers, known_companies)
        assert result == ["AAPL"]

    def test_returns_empty_for_no_match(self) -> None:
        known_tickers = {"AAPL", "NVDA"}
        known_companies = {"Apple Inc": "AAPL"}
        result = detect_query_tickers("What is the meaning of life?", known_tickers, known_companies)
        assert result == []


# ---------------------------------------------------------------------------
# RetrievalIndex
# ---------------------------------------------------------------------------


class TestRetrievalIndex:
    """RetrievalIndex precomputation."""

    def test_index_builds_from_chunks(self) -> None:
        """Index should precompute BM25 data and known tickers."""
        emb = list(np.random.default_rng(42).random(8))
        c1 = _make_chunk("c1", "Apple revenue grew", ticker="AAPL", company="Apple Inc", embedding=emb)
        c2 = _make_chunk("c2", "NVIDIA data center", ticker="NVDA", company="NVIDIA Corporation", embedding=emb)

        idx = RetrievalIndex([c1, c2])
        assert "AAPL" in idx.known_tickers
        assert "NVDA" in idx.known_tickers
        assert "Apple Inc" in idx.known_companies
        assert idx.embedding_matrix is not None
        assert idx.embedding_matrix.shape == (2, 8)

    def test_index_with_no_embeddings(self) -> None:
        """Index with chunks that have no embeddings should still work for BM25."""
        c1 = _make_chunk("c1", "Some text here")
        idx = RetrievalIndex([c1])
        assert idx.embedding_matrix is None
        assert len(idx.tokenized_docs) == 1


# ---------------------------------------------------------------------------
# Vector search with precomputed index
# ---------------------------------------------------------------------------


class TestVectorSearch:
    """Vector search using the vectorized matmul path."""

    @patch("src.retrieve.traced_embedding")
    def test_vector_search_ranks_by_cosine_similarity(self, mock_embed) -> None:
        """Chunks with embeddings closer to query should rank higher."""
        # Query embedding points in direction [1, 0, 0]
        mock_embed.return_value = [[1.0, 0.0, 0.0]]

        c1 = _make_chunk("c1", "close match", embedding=[0.9, 0.1, 0.0])
        c2 = _make_chunk("c2", "far match", embedding=[0.1, 0.9, 0.0])
        c3 = _make_chunk("c3", "medium match", embedding=[0.5, 0.5, 0.0])
        chunks = [c1, c2, c3]

        idx = RetrievalIndex(chunks)
        results = _vector_search("test query", chunks, top_k=3, index=idx)

        assert len(results) == 3
        # c1 is closest to [1,0,0], c3 is medium, c2 is farthest
        assert results[0]["chunk"].chunk_id == "c1"
        assert results[2]["chunk"].chunk_id == "c2"
        assert results[0]["score"] > results[1]["score"] > results[2]["score"]


# ---------------------------------------------------------------------------
# Multi-company retrieval
# ---------------------------------------------------------------------------


class TestMultiCompanyRetrieval:
    """Multi-company queries should retrieve from each mentioned company."""

    @patch("src.retrieve.traced_embedding")
    def test_multi_company_returns_both_tickers(self, mock_embed) -> None:
        """A query mentioning Apple and NVIDIA should return chunks from both."""
        # All embeddings similar so BM25 drives ranking
        emb = [0.5, 0.5, 0.5]
        mock_embed.return_value = [emb]

        # 3 Apple chunks, 3 NVIDIA chunks — Apple text slightly more relevant
        apple_chunks = [
            _make_chunk(f"a{i}", f"Apple risk factors include supply chain issues part {i}",
                        ticker="AAPL", company="Apple Inc", embedding=emb)
            for i in range(3)
        ]
        nvda_chunks = [
            _make_chunk(f"n{i}", f"NVIDIA risk factors include export controls part {i}",
                        ticker="NVDA", company="NVIDIA Corporation", embedding=emb)
            for i in range(3)
        ]
        chunks = apple_chunks + nvda_chunks
        idx = RetrievalIndex(chunks)

        results = retrieve(
            "What are the risk factors facing Apple and NVIDIA?",
            chunks=chunks,
            index=idx,
        )

        tickers_in_results = {r["chunk"].ticker for r in results}
        assert "AAPL" in tickers_in_results, "Apple chunks missing from results"
        assert "NVDA" in tickers_in_results, "NVIDIA chunks missing from results"


# ---------------------------------------------------------------------------
# BM25 with precomputed index
# ---------------------------------------------------------------------------


class TestBM25Precomputed:
    """BM25 scoring using the precomputed index path."""

    def test_bm25_with_index_scores_relevant_higher(self) -> None:
        """Precomputed BM25 should rank matching chunks higher."""
        relevant = _make_chunk("c1", "NVIDIA revenue grew significantly in fiscal year 2025")
        irrelevant = _make_chunk("c2", "The weather today is sunny and warm outside")
        chunks = [relevant, irrelevant]
        idx = RetrievalIndex(chunks)

        results = _bm25_search("NVIDIA revenue", chunks, top_k=5, index=idx)
        assert len(results) >= 1
        assert results[0]["chunk"].chunk_id == "c1"
