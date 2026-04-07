"""Generate — LLM answer synthesis with mandatory citations."""

import json
import logging

from src.prompts import SYSTEM_PROMPT
from src.telemetry import traced_llm_call

logger = logging.getLogger(__name__)


def generate_answer(question: str, retrieved: list[dict]) -> dict:
    """
    Generate a cited answer from retrieved chunks. Refuse if evidence is weak.

    Args:
        question: the user's question
        retrieved: list of {"chunk": Chunk, "score": float} from retrieve()

    Returns:
        Parsed response dict with answer, citations, confidence, refusal_reason.
    """
    if not retrieved:
        return {
            "answer": None,
            "citations": [],
            "confidence": "low",
            "refusal_reason": "No relevant documents found for this question.",
        }

    # Build context from retrieved chunks
    context_parts = []
    for i, r in enumerate(retrieved):
        chunk = r["chunk"]
        source_info = f"{chunk.ticker} {chunk.filing_type} {chunk.filing_date}"
        section_info = f", {chunk.section_name}" if chunk.section_name else ""
        context_parts.append(
            f"[Chunk {i+1}] Source: {source_info}{section_info} ({chunk.doc_name})\n{chunk.text}"
        )
    context = "\n\n---\n\n".join(context_parts)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]

    result = traced_llm_call(
        messages=messages,
        response_format={"type": "json_object"},
        label="generate_answer",
    )

    try:
        parsed = json.loads(result["content"])
    except (json.JSONDecodeError, TypeError):
        logger.error(f"Failed to parse LLM response as JSON: {result['content'][:200]}")
        return {
            "answer": None,
            "citations": [],
            "confidence": "low",
            "refusal_reason": "System error: could not parse response.",
        }

    # Ensure required fields exist
    parsed.setdefault("answer", None)
    parsed.setdefault("citations", [])
    parsed.setdefault("confidence", "low")
    parsed.setdefault("refusal_reason", None)

    # Add telemetry metadata
    parsed["_telemetry"] = {
        "model": result["model"],
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "latency_ms": result["latency_ms"],
    }

    return parsed
