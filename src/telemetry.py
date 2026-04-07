"""Lightweight telemetry — every LLM call goes through here."""

import logging
import time
from typing import Any

from openai import OpenAI

from src.config import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None
_call_log: list[dict[str, Any]] = []


def get_client() -> OpenAI:
    """Lazy-init OpenAI client."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.openai_api_key)
    return _client


def traced_llm_call(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.0,
    response_format: dict | None = None,
    label: str = "llm_call",
) -> dict[str, Any]:
    """
    Single entry point for all LLM calls. Tracks latency, tokens, cost.

    Returns the full API response dict with added telemetry fields.
    """
    model = model or config.model_id
    client = get_client()

    start = time.time()
    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = client.chat.completions.create(**kwargs)
        latency_ms = (time.time() - start) * 1000

        result = {
            "content": response.choices[0].message.content,
            "model": response.model,
            "tokens_in": response.usage.prompt_tokens if response.usage else 0,
            "tokens_out": response.usage.completion_tokens if response.usage else 0,
            "latency_ms": round(latency_ms, 1),
            "label": label,
        }

        _call_log.append(result)
        logger.info(
            f"[{label}] {result['model']} — "
            f"{result['tokens_in']}in/{result['tokens_out']}out — "
            f"{result['latency_ms']}ms"
        )
        return result

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.error(f"[{label}] LLM call failed after {latency_ms:.0f}ms: {e}")
        raise


def traced_embedding(texts: list[str], label: str = "embed") -> list[list[float]]:
    """Embed texts with telemetry."""
    client = get_client()
    start = time.time()

    response = client.embeddings.create(
        model=config.embedding_model,
        input=texts,
        dimensions=config.embedding_dimensions,
    )
    latency_ms = (time.time() - start) * 1000

    embeddings = [item.embedding for item in response.data]
    logger.info(f"[{label}] Embedded {len(texts)} texts — {latency_ms:.0f}ms")

    _call_log.append({
        "label": label,
        "count": len(texts),
        "latency_ms": round(latency_ms, 1),
    })
    return embeddings


def get_call_log() -> list[dict[str, Any]]:
    """Return all traced calls for this session."""
    return _call_log.copy()


def reset_call_log() -> None:
    """Clear the call log (useful between eval runs)."""
    _call_log.clear()
