"""Tests for generate_answer normalization and schema handling."""

from unittest.mock import patch

from src.generate import generate_answer
from src.ingest import Chunk


def _make_chunk(
    chunk_id: str,
    text: str,
    ticker: str = "AAPL",
    company: str = "Apple Inc",
    filing_type: str = "10-K",
    filing_date: str = "2025-01-01",
    section_name: str = "Item 7",
) -> Chunk:
    """Build a minimal chunk for generation tests."""
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        doc_name=f"{ticker}_10K_{filing_date}_full.txt",
        ticker=ticker,
        company=company,
        filing_type=filing_type,
        filing_date=filing_date,
        section_name=section_name,
        embedding=[],
    )


def _retrieved_chunks() -> list[dict]:
    """Return a small retrieval set with citations the model can reference."""
    aapl = _make_chunk(
        "aapl-1",
        "Apple emphasizes market and credit risk exposures.",
        ticker="AAPL",
        company="Apple Inc",
        filing_date="2024-11-01",
        section_name="Item 1A",
    )
    pfe = _make_chunk(
        "pfe-1",
        "Pfizer emphasizes foreign exchange and interest rate risk.",
        ticker="PFE",
        company="Pfizer Inc",
        filing_type="10-Q",
        filing_date="2025-02-15",
        section_name="Part I - Item 1A",
    )
    return [
        {"chunk": aapl, "score": 0.9},
        {"chunk": pfe, "score": 0.88},
    ]


class TestGenerateAnswerSchema:
    """Regression tests for output normalization in generate_answer."""

    @patch("src.generate.traced_llm_call")
    def test_valid_top_level_json_is_preserved(self, mock_llm) -> None:
        """Flat answer/citations output should pass through unchanged."""
        mock_llm.return_value = {
            "content": (
                '{"answer":"Apple emphasizes market and credit risk.",'
                '"citations":[{"ticker":"AAPL","filing_type":"10-K","filing_date":"2024-11-01",'
                '"section":"Item 1A","doc_name":"AAPL_10K_2024-11-01_full.txt",'
                '"quoted_text":"Apple emphasizes market and credit risk."}],'
                '"confidence":"high","refusal_reason":null}'
            ),
            "model": "gpt-5.4-mini",
            "tokens_in": 100,
            "tokens_out": 50,
            "latency_ms": 10,
        }

        result = generate_answer("What risks does Apple emphasize?", _retrieved_chunks())

        assert result["answer"] == "Apple emphasizes market and credit risk."
        assert result["confidence"] == "high"
        assert result["refusal_reason"] is None
        assert len(result["citations"]) == 1
        assert result["citations"][0]["ticker"] == "AAPL"
        assert "_telemetry" in result

    @patch("src.generate.traced_llm_call")
    def test_nested_company_json_is_flattened(self, mock_llm) -> None:
        """Nested per-company answers should be normalized to a plain-text top-level answer."""
        mock_llm.return_value = {
            "content": (
                "{"
                '"AAPL":{"answer":"Apple emphasizes market and credit risk.",'
                '"citations":[{"ticker":"AAPL","filing_type":"10-K","filing_date":"2024-11-01",'
                '"section":"Item 1A","doc_name":"AAPL_10K_2024-11-01_full.txt",'
                '"quoted_text":"Apple emphasizes market and credit risk."}],"confidence":"high",'
                '"refusal_reason":null},'
                '"PFE":{"answer":"Pfizer emphasizes foreign exchange and interest rate risk.",'
                '"citations":[{"ticker":"PFE","filing_type":"10-Q","filing_date":"2025-02-15",'
                '"section":"Part I - Item 1A","doc_name":"PFE_10Q_2025-02-15_full.txt",'
                '"quoted_text":"Pfizer emphasizes foreign exchange and interest rate risk."}],"confidence":"high",'
                '"refusal_reason":null},'
                '"comparative_summary":"Apple emphasizes market and credit risk, '
                'while Pfizer emphasizes foreign exchange and interest rate risk."'
                "}"
            ),
            "model": "gpt-5.4-mini",
            "tokens_in": 100,
            "tokens_out": 140,
            "latency_ms": 10,
        }

        result = generate_answer("Compare Apple and Pfizer risk factors.", _retrieved_chunks())

        assert isinstance(result["answer"], str)
        assert result["answer"].strip().startswith("AAPL")
        assert "PFE" in result["answer"]
        assert "comparative summary" in result["answer"].lower()
        assert result["citations"], "Nested citations should be merged into the top-level array"
        assert {c["ticker"] for c in result["citations"]} == {"AAPL", "PFE"}
        assert result["confidence"] == "high"

    @patch("src.generate.traced_llm_call")
    def test_answer_object_with_nested_company_json_is_normalized(self, mock_llm) -> None:
        """An object-valued answer field should still flatten into text and citations."""
        mock_llm.return_value = {
            "content": (
                "{"
                '"answer":{'
                '"AAPL":{"answer":"Apple emphasizes market and credit risk.",'
                '"citations":[{"ticker":"AAPL","filing_type":"10-K","filing_date":"2024-11-01",'
                '"section":"Item 1A","doc_name":"AAPL_10K_2024-11-01_full.txt",'
                '"quoted_text":"Apple emphasizes market and credit risk."}],"confidence":"high",'
                '"refusal_reason":null},'
                '"PFE":{"answer":"Pfizer emphasizes foreign exchange and interest rate risk.",'
                '"citations":[{"ticker":"PFE","filing_type":"10-Q","filing_date":"2025-02-15",'
                '"section":"Part I - Item 1A","doc_name":"PFE_10Q_2025-02-15_full.txt",'
                '"quoted_text":"Pfizer emphasizes foreign exchange and interest rate risk."}],"confidence":"high",'
                '"refusal_reason":null},'
                '"comparative_summary":"Apple emphasizes market and credit risk, '
                'while Pfizer emphasizes foreign exchange and interest rate risk."'
                '},'
                '"citations":[],"confidence":"high","refusal_reason":null'
                "}"
            ),
            "model": "gpt-5.4-mini",
            "tokens_in": 100,
            "tokens_out": 150,
            "latency_ms": 10,
        }

        result = generate_answer("Compare Apple and Pfizer risk factors.", _retrieved_chunks())

        assert isinstance(result["answer"], str)
        assert result["answer"].strip().startswith("AAPL")
        assert "PFE" in result["answer"]
        assert "comparative summary" in result["answer"].lower()
        assert result["citations"], "Nested citations should be merged into the top-level array"
        assert {c["ticker"] for c in result["citations"]} == {"AAPL", "PFE"}
        assert result["confidence"] == "high"

    @patch("src.generate.traced_llm_call")
    def test_stringified_nested_json_in_answer_is_normalized(self, mock_llm) -> None:
        """Stringified nested JSON inside answer should be flattened into readable text."""
        mock_llm.return_value = {
            "content": (
                '{"answer":"{\\"AAPL\\": {\\"answer\\": \\"Apple emphasizes market risk.\\", '
                '\\"citations\\": [{\\"ticker\\": \\"AAPL\\", \\"filing_type\\": \\"10-K\\", '
                '\\"filing_date\\": \\"2024-11-01\\", \\"section\\": \\"Item 1A\\", '
                '\\"doc_name\\": \\"AAPL_10K_2024-11-01_full.txt\\", '
                '\\"quoted_text\\": \\"Apple emphasizes market risk.\\"}]}}",'
                '"citations":[],"confidence":"high","refusal_reason":null}'
            ),
            "model": "gpt-5.4-mini",
            "tokens_in": 100,
            "tokens_out": 120,
            "latency_ms": 10,
        }

        result = generate_answer("What risks does Apple emphasize?", _retrieved_chunks())

        assert isinstance(result["answer"], str)
        assert result["answer"].strip().startswith("AAPL")
        assert "Apple emphasizes market risk." in result["answer"]
        assert result["citations"], "Stringified nested citations should be recovered"
        assert result["citations"][0]["ticker"] == "AAPL"
        assert result["confidence"] == "high"
