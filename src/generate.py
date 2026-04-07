"""Generate — LLM answer synthesis with mandatory citations."""

import json
import logging

from src.telemetry import traced_llm_call

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a document question-answering assistant.

RULES — follow these exactly:
1. Answer ONLY based on the provided context chunks. Do not use outside knowledge.
2. Every claim must cite the source using [doc_name, page] format.
3. If the context does not contain enough information to answer, respond with:
   {"answer": null, "refusal_reason": "Insufficient evidence in the provided documents.", "citations": []}
4. Keep answers concise and factual.

Respond in this exact JSON format:
{
  "answer": "Your answer with inline [doc, page] citations",
  "citations": [
    {
      "doc_name": "document.pdf",
      "page": 5,
      "quoted_text": "exact short quote from the source that supports your claim"
    }
  ],
  "confidence": "high" | "medium" | "low",
  "refusal_reason": null
}
"""


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
        page_info = f", page {chunk.page}" if chunk.page else ""
        context_parts.append(
            f"[Chunk {i+1}] Source: {chunk.doc_name}{page_info}\n{chunk.text}"
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
