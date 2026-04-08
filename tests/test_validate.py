"""Tests for citation validation — Jaccard similarity and substring matching."""

from src.ingest import Chunk
from src.validate import _jaccard_similarity, validate_citations


def _make_chunk(text: str) -> dict:
    """Build a minimal retrieval result for validation tests."""
    return {
        "chunk": Chunk(
            chunk_id="test::1",
            text=text,
            doc_name="TEST_10K_2025-01-01_full.txt",
            ticker="TEST",
            company="Test Corp",
            filing_type="10-K",
            filing_date="2025-01-01",
            section_name="Item 7",
        ),
        "score": 0.9,
        "method": "hybrid",
    }


class TestJaccardSimilarity:
    """Jaccard similarity edge cases."""

    def test_jaccard_identical(self) -> None:
        assert _jaccard_similarity("hello world", "hello world") == 1.0

    def test_jaccard_no_overlap(self) -> None:
        assert _jaccard_similarity("hello world", "foo bar") == 0.0

    def test_jaccard_partial(self) -> None:
        score = _jaccard_similarity("apple orange banana", "apple orange grape")
        # intersection=2 (apple, orange), union=4 (apple, orange, banana, grape)
        assert abs(score - 0.5) < 0.01

    def test_jaccard_empty(self) -> None:
        assert _jaccard_similarity("", "hello") == 0.0
        assert _jaccard_similarity("hello", "") == 0.0


class TestValidateCitations:
    """Citation validation with substring and Jaccard matching."""

    def test_exact_substring_match(self) -> None:
        """Citation that appears verbatim in chunk should be valid."""
        retrieved = [_make_chunk("Revenue for fiscal year 2025 was $130.5 billion.")]
        response = {
            "answer": "Revenue was $130.5 billion.",
            "citations": [{"quoted_text": "Revenue for fiscal year 2025 was $130.5 billion."}],
        }
        result = validate_citations(response, retrieved)
        assert result["citations"][0]["valid"] is True
        assert result["citations_valid"] is True
        assert "Exact match" in result["citations"][0]["validation_note"]

    def test_below_threshold_flagged(self) -> None:
        """Citation with no match in any chunk should be invalid."""
        retrieved = [_make_chunk("The weather is sunny today.")]
        response = {
            "answer": "Revenue grew.",
            "citations": [{"quoted_text": "Revenue for fiscal year 2025 was $130.5 billion."}],
        }
        result = validate_citations(response, retrieved)
        assert result["citations"][0]["valid"] is False
        assert result["citations_valid"] is False

    def test_no_quoted_text(self) -> None:
        """Citation without quoted_text should be flagged invalid."""
        retrieved = [_make_chunk("Some text.")]
        response = {
            "answer": "An answer.",
            "citations": [{"ticker": "TEST"}],
        }
        result = validate_citations(response, retrieved)
        assert result["citations"][0]["valid"] is False
        assert "No quoted text" in result["citations"][0]["validation_note"]

    def test_empty_citations_returns_unchanged(self) -> None:
        """Response with no citations should pass through unchanged."""
        response = {"answer": "An answer.", "citations": []}
        result = validate_citations(response, [])
        assert "citations_valid" not in result
