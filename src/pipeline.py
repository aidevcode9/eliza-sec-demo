"""Pipeline — orchestrate the full RAG flow."""

import logging

from src.generate import generate_answer
from src.ingest import Chunk
from src.retrieve import retrieve
from src.validate import check_negation_mismatch, validate_citations

logger = logging.getLogger(__name__)

# Simple injection patterns
INJECTION_PATTERNS = [
    "ignore your instructions",
    "ignore previous instructions",
    "system prompt",
    "you are now",
    "pretend you are",
    "disregard",
    "override",
]


def ask(question: str, chunks: list[Chunk] | None = None) -> dict:
    """
    Full RAG pipeline: inject check → retrieve → generate → validate.

    Returns response dict with answer, citations, confidence, refusal_reason,
    and metadata about retrieval and validation.
    """
    # Step 1: Injection check
    if _is_injection(question):
        logger.warning(f"Injection attempt detected: {question[:50]}...")
        return {
            "answer": None,
            "citations": [],
            "confidence": "low",
            "refusal_reason": "This question could not be processed.",
            "retrieval": [],
        }

    # Step 2: Retrieve
    results = retrieve(question, chunks=chunks)

    if not results:
        return {
            "answer": None,
            "citations": [],
            "confidence": "low",
            "refusal_reason": "No relevant documents found for this question.",
            "retrieval": [
                {"doc_name": r["chunk"].doc_name, "score": r["score"]}
                for r in results
            ],
        }

    # Step 3: Generate with citation enforcement
    response = generate_answer(question, results)

    # Step 4: Validate citations
    response = validate_citations(response, results)
    response = check_negation_mismatch(response, results)

    # Add retrieval metadata
    response["retrieval"] = [
        {
            "doc_name": r["chunk"].doc_name,
            "ticker": r["chunk"].ticker,
            "filing_type": r["chunk"].filing_type,
            "section_name": r["chunk"].section_name,
            "score": round(r["score"], 4),
            "text_preview": r["chunk"].text[:100] + "...",
        }
        for r in results
    ]

    return response


def _is_injection(question: str) -> bool:
    """Basic prompt injection filter."""
    q_lower = question.lower()
    return any(pattern in q_lower for pattern in INJECTION_PATTERNS)
