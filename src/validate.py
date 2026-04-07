"""Validate — verify citations actually exist in source chunks."""

import logging

from src.config import config

logger = logging.getLogger(__name__)


def validate_citations(response: dict, retrieved: list[dict]) -> dict:
    """
    Check that each citation's quoted_text actually appears in the retrieved chunks.

    Uses Jaccard similarity for fuzzy matching (LLM may paraphrase slightly).
    Adds validation status to each citation and overall response.
    """
    if not response.get("citations"):
        return response

    chunk_texts = {r["chunk"].doc_name: r["chunk"].text for r in retrieved}
    # Also index by chunk for more granular matching
    all_chunk_texts = [r["chunk"].text for r in retrieved]

    validated_citations = []
    all_valid = True

    for citation in response["citations"]:
        quoted = citation.get("quoted_text", "")
        doc_name = citation.get("doc_name", "")

        if not quoted:
            citation["valid"] = False
            citation["validation_note"] = "No quoted text provided"
            all_valid = False
            validated_citations.append(citation)
            continue

        # Check against all retrieved chunks
        best_score = 0.0
        best_chunk_doc = None
        for r in retrieved:
            score = _jaccard_similarity(quoted, r["chunk"].text)
            if score > best_score:
                best_score = score
                best_chunk_doc = r["chunk"].doc_name

        # Also check for substring match (exact quote in chunk)
        substring_match = any(
            quoted.lower() in r["chunk"].text.lower()
            for r in retrieved
        )

        if substring_match:
            citation["valid"] = True
            citation["validation_note"] = "Exact match found"
            citation["jaccard_score"] = best_score
        elif best_score >= config.jaccard_threshold:
            citation["valid"] = True
            citation["validation_note"] = f"Fuzzy match (jaccard={best_score:.2f})"
            citation["jaccard_score"] = best_score
        else:
            citation["valid"] = False
            citation["validation_note"] = (
                f"Quote not found in sources (best jaccard={best_score:.2f}, "
                f"threshold={config.jaccard_threshold})"
            )
            citation["jaccard_score"] = best_score
            all_valid = False

        validated_citations.append(citation)

    response["citations"] = validated_citations
    response["citations_valid"] = all_valid

    if not all_valid:
        invalid_count = sum(1 for c in validated_citations if not c.get("valid"))
        logger.warning(f"Citation validation: {invalid_count} invalid citations found")

    return response


def check_negation_mismatch(response: dict, retrieved: list[dict]) -> dict:
    """
    Detect negation mismatches: answer says X, but source says NOT X.

    Simple heuristic: check if answer and source disagree on key negation words.
    """
    answer = response.get("answer", "") or ""
    if not answer:
        return response

    negation_words = {"not", "no", "never", "none", "neither", "nor", "cannot", "doesn't", "don't", "isn't", "wasn't", "aren't", "won't"}
    answer_lower = answer.lower()
    answer_has_negation = any(w in answer_lower.split() for w in negation_words)

    for r in retrieved:
        chunk_lower = r["chunk"].text.lower()
        chunk_has_negation = any(w in chunk_lower.split() for w in negation_words)

        # Flag if answer and chunk disagree on negation for same key terms
        if answer_has_negation != chunk_has_negation:
            # Simple check: find shared noun phrases
            answer_words = set(answer_lower.split()) - negation_words
            chunk_words = set(chunk_lower.split()) - negation_words
            overlap = answer_words & chunk_words

            if len(overlap) > 3:  # enough shared context to matter
                response.setdefault("_warnings", []).append(
                    f"Possible negation mismatch with {r['chunk'].doc_name}: "
                    f"answer {'contains' if answer_has_negation else 'lacks'} negation, "
                    f"source {'contains' if chunk_has_negation else 'lacks'} negation"
                )
                logger.warning(f"Negation mismatch detected with {r['chunk'].doc_name}")

    return response


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Token-level Jaccard similarity between two texts."""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)
