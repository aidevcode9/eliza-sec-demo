"""Generate - LLM answer synthesis with mandatory citations."""

import json
import logging
from typing import Any

from src.config import config
from src.prompts import SYSTEM_PROMPT
from src.telemetry import traced_llm_call

logger = logging.getLogger(__name__)

_STANDARD_RESPONSE_KEYS = {"answer", "citations", "confidence", "refusal_reason"}
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _titleize_key(key: str) -> str:
    """Convert machine-style keys into readable section headers."""
    cleaned = key.replace("_", " ").replace("-", " ").strip()
    if not cleaned:
        return "Section"
    return cleaned if cleaned.isupper() else cleaned.capitalize()


def _parse_json_like_string(value: object) -> dict[str, Any] | list[Any] | None:
    """Parse a JSON-like string if it contains an object or array."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _looks_like_citation(item: object) -> bool:
    """Return True for citation-shaped dicts."""
    return isinstance(item, dict) and (
        "quoted_text" in item
        or bool({"ticker", "filing_type", "filing_date", "section", "doc_name"} & set(item.keys()))
    )


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate citations while preserving order."""
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for citation in citations:
        key = (
            citation.get("ticker"),
            citation.get("filing_type"),
            citation.get("filing_date"),
            citation.get("section"),
            citation.get("doc_name"),
            citation.get("quoted_text"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)

    return deduped


def _collect_nested_citations(value: object) -> list[dict[str, Any]]:
    """Collect citations from nested company-style payloads."""
    collected: list[dict[str, Any]] = []

    if isinstance(value, list):
        for item in value:
            collected.extend(_collect_nested_citations(item))
        return collected

    if not isinstance(value, dict):
        return collected

    if _looks_like_citation(value):
        return [value]

    for key, nested in value.items():
        if key in {"citations", "evidence"}:
            collected.extend(_collect_nested_citations(nested))
        elif isinstance(nested, (dict, list)):
            collected.extend(_collect_nested_citations(nested))

    return collected


def _collect_nested_confidences(value: object) -> list[str]:
    """Collect nested confidence values for conservative aggregation."""
    confidences: list[str] = []

    if isinstance(value, list):
        for item in value:
            confidences.extend(_collect_nested_confidences(item))
        return confidences

    if not isinstance(value, dict):
        return confidences

    confidence = value.get("confidence")
    if isinstance(confidence, str):
        normalized = confidence.lower().strip()
        if normalized in _CONFIDENCE_RANK:
            confidences.append(normalized)

    for nested in value.values():
        if isinstance(nested, (dict, list)):
            confidences.extend(_collect_nested_confidences(nested))

    return confidences


def _format_scalar(value: object) -> str:
    """Render scalar values consistently."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).strip()


def _summarize_nested_value(value: object) -> str:
    """Convert nested JSON values into readable plain text."""
    if isinstance(value, dict):
        if isinstance(value.get("answer"), str) and value["answer"].strip():
            return value["answer"].strip()

        parts: list[str] = []
        for key, item in value.items():
            if key in {"citations", "evidence", "confidence", "refusal_reason"}:
                continue
            summary = _summarize_nested_value(item)
            if summary:
                parts.append(f"{_titleize_key(key)}: {summary}")

        if not parts and isinstance(value.get("refusal_reason"), str):
            return value["refusal_reason"].strip()
        return "\n".join(parts)

    if isinstance(value, list):
        summaries = [_summarize_nested_value(item) for item in value]
        cleaned = [summary for summary in summaries if summary]
        return "; ".join(cleaned)

    scalar = _format_scalar(value)
    return "" if scalar == "None" else scalar


def _flatten_nested_payload(payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Flatten a nested multi-company payload into the top-level response contract."""
    sections: list[str] = []
    citations = _dedupe_citations(_collect_nested_citations(payload))
    confidences = _collect_nested_confidences(payload)

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _STANDARD_RESPONSE_KEYS:
                continue
            summary = _summarize_nested_value(value)
            if not summary:
                continue
            if key == "comparative_summary":
                sections.append(f"Comparative summary: {summary}")
            else:
                sections.append(f"{key}:\n{summary}")
    else:
        summary = _summarize_nested_value(payload)
        if summary:
            sections.append(summary)

    answer = "\n\n".join(section.strip() for section in sections if section.strip())
    confidence = None
    if confidences:
        confidence = min(confidences, key=lambda item: _CONFIDENCE_RANK[item])

    return {
        "answer": answer or None,
        "citations": citations,
        "confidence": confidence,
    }


def _normalize_multi_company_shape(parsed: dict[str, Any]) -> dict[str, Any]:
    """Recover nested multi-company outputs into the flat response contract."""
    extra_keys = [key for key in parsed if key not in _STANDARD_RESPONSE_KEYS]
    nested_answer_payload = _parse_json_like_string(parsed.get("answer"))

    nested_payload: dict[str, Any] | list[Any] | None = None
    if nested_answer_payload is not None:
        nested_payload = nested_answer_payload
    elif extra_keys:
        nested_payload = {key: parsed[key] for key in extra_keys}

    if nested_payload is None:
        return parsed

    flattened = _flatten_nested_payload(nested_payload)
    if flattened.get("answer"):
        parsed["answer"] = flattened["answer"]

    top_level_citations = parsed.get("citations")
    merged_citations: list[dict[str, Any]] = []
    if isinstance(top_level_citations, list):
        merged_citations.extend(
            citation for citation in top_level_citations if isinstance(citation, dict)
        )
    merged_citations.extend(flattened["citations"])
    parsed["citations"] = _dedupe_citations(merged_citations)

    if flattened.get("confidence") in _CONFIDENCE_RANK:
        parsed["confidence"] = flattened["confidence"]

    return parsed


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
        max_tokens=config.max_tokens,
        label="generate_answer",
    )

    if result.get("content") is None:
        logger.error("LLM returned null content")
        return {
            "answer": None,
            "citations": [],
            "confidence": "low",
            "refusal_reason": "System error: LLM returned no content.",
        }

    try:
        parsed = json.loads(result["content"])
    except (json.JSONDecodeError, TypeError):
        logger.error(
            "Failed to parse LLM response as JSON: %s",
            str(result.get("content", ""))[:200],
        )
        return {
            "answer": None,
            "citations": [],
            "confidence": "low",
            "refusal_reason": "System error: could not parse response.",
        }

    parsed = _normalize_multi_company_shape(parsed)

    parsed.setdefault("answer", None)
    parsed.setdefault("citations", [])
    parsed.setdefault("confidence", "low")
    parsed.setdefault("refusal_reason", None)

    parsed["confidence"] = str(parsed.get("confidence", "low")).lower().strip()

    # Low confidence now means weak evidence, not automatic refusal.
    # Keep the answer visible when present, but attach a warning for the UI.
    if parsed["confidence"] == "low" and parsed.get("answer") is not None:
        logger.warning("Low confidence answer - weak evidence warning attached")
        parsed.setdefault("_warning", "Weak evidence: the answer may be incomplete, ambiguous, or imprecise.")

    parsed["_telemetry"] = {
        "model": result["model"],
        "tokens_in": result["tokens_in"],
        "tokens_out": result["tokens_out"],
        "latency_ms": result["latency_ms"],
    }

    return parsed
