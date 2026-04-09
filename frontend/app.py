"""Streamlit frontend for the SEC Filing RAG demo."""

from __future__ import annotations

import html
import json
import logging
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import config  # noqa: E402
from src.ingest import Chunk, load_chunks  # noqa: E402
from src.pipeline import ask  # noqa: E402
from src.retrieve import RetrievalIndex  # noqa: E402

logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

EXAMPLE_QUESTIONS = {
    "Single-company": "What was NVIDIA's total revenue for fiscal year 2025?",
    "Cross-company": "Compare the risk factors of Apple and Pfizer. What types of risks does each company emphasize?",
    "Refusal": "What is the current stock price of NVIDIA?",
}

CONFIDENCE_GUIDE = {
    "HIGH": "Directly stated in the retrieved filings and supported by clear evidence.",
    "MEDIUM": "Supported by the retrieved filings, but requires some interpretation or synthesis.",
    "LOW": "Evidence is weak, incomplete, or ambiguous. An answer may still be shown, but it should be treated cautiously.",
}


@st.cache_resource(show_spinner=False)
def load_runtime() -> tuple[list[Chunk], RetrievalIndex]:
    """Load chunks and build the retrieval index once for the app session."""
    chunks = load_chunks()
    index = RetrievalIndex(chunks)
    logger.info("Frontend loaded %d chunks and built retrieval index", len(chunks))
    return chunks, index


def set_example(question: str) -> None:
    """Populate the input box with a demo question."""
    st.session_state["question_input"] = question


def _render_card(title: str, body: str | None = None, card_class: str = "") -> None:
    """Render a styled panel card."""
    body_html = ""
    if body:
        body_html = f'<div class="card-body">{html.escape(body).replace(chr(10), "<br>")}</div>'

    st.markdown(
        f"""
        <div class="result-card {card_class}">
            <div class="result-title">{html.escape(title)}</div>
            {body_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_top_stat_pills(chunks: list[Chunk]) -> None:
    """Render compact top-of-page stats without dominating the layout."""
    file_count = len({chunk.doc_name for chunk in chunks})
    stats = [
        ("Files loaded", f"{file_count:,}"),
        ("Chunks loaded", f"{len(chunks):,}"),
        ("Model", config.model_id),
    ]
    pills = "".join(
        f"""
        <div class="top-stat-pill">
            <span class="top-stat-label">{html.escape(label)}</span>
            <span class="top-stat-value">{html.escape(value)}</span>
        </div>
        """
        for label, value in stats
    )
    st.markdown(
        f"""
        <div class="top-stat-row">{pills}</div>
        <div class="top-stat-note">Retrieval depth: top {config.top_k} evidence chunks per question.</div>
        """,
        unsafe_allow_html=True,
    )


def _render_retrieval_preview(text: str) -> None:
    """Render retrieval previews as literal text, not markdown/math."""
    st.markdown(
        f'<div class="retrieval-preview">{html.escape(text).replace(chr(10), "<br>")}</div>',
        unsafe_allow_html=True,
    )


def render_citation(citation: dict, number: int) -> None:
    """Render a human-readable citation card."""
    badge_parts = []
    if "valid" in citation:
        badge_parts.append("Validated" if citation.get("valid") else "Needs review")

    meta = " | ".join(
        part
        for part in (
            citation.get("ticker"),
            citation.get("filing_type"),
            citation.get("filing_date"),
            citation.get("section"),
        )
        if part
    )
    quote = citation.get("quoted_text") or "No supporting quote provided."

    footer_parts = []
    if citation.get("doc_name"):
        footer_parts.append(str(citation["doc_name"]))
    if badge_parts:
        footer_parts.append(" | ".join(badge_parts))
    if citation.get("valid") is True:
        footer_parts.append("Source quote verified")
    elif citation.get("valid") is False:
        footer_parts.append("Source quote may need manual review")

    footer_html = ""
    if footer_parts:
        footer_html = f'<div class="result-meta">{html.escape(" | ".join(footer_parts))}</div>'

    st.markdown(
        f"""
        <div class="result-card citation-card">
            <div class="result-title">[{number}] {html.escape(meta or "Citation")}</div>
            <div class="citation-quote">{html.escape(quote)}</div>
            {footer_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _format_label(label: str) -> str:
    """Convert machine-style keys into human-readable labels."""
    cleaned = label.replace("_", " ").replace("-", " ").strip()
    if not cleaned:
        return "Value"
    return cleaned if cleaned.isupper() else cleaned.title()


def _scalar_text(value: object) -> str:
    """Render scalar values consistently for display."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _maybe_parse_structured_answer(answer: object) -> dict | list | None:
    """Parse JSON-like answers so they can be rendered as sections instead of a blob."""
    if isinstance(answer, (dict, list)):
        return answer
    if not isinstance(answer, str):
        return None

    stripped = answer.strip()
    if not stripped or stripped[0] not in "{[":
        return None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, (dict, list)) else None


def _is_scalar(value: object) -> bool:
    """Return True when the value can be rendered inline."""
    return value is None or isinstance(value, (str, int, float, bool))


def _looks_like_evidence(value: object) -> bool:
    """Detect evidence-shaped dicts so they can render as quote blocks."""
    return isinstance(value, dict) and (
        "quoted_text" in value
        or {"ticker", "filing_type", "filing_date", "section", "doc_name"} & set(value.keys())
    )


def _render_evidence_html(value: dict) -> str:
    """Render a citation-like evidence object inside the answer body."""
    meta = " | ".join(
        part
        for part in (
            value.get("ticker"),
            value.get("filing_type"),
            value.get("filing_date"),
            value.get("section"),
        )
        if part
    )
    footer = html.escape(str(value.get("doc_name", "")))
    quote = html.escape(str(value.get("quoted_text") or value.get("text") or "No evidence text provided."))

    footer_html = ""
    if footer:
        footer_html = f'<div class="structured-evidence-footer">{footer}</div>'

    return f"""
    <div class="structured-evidence">
        <div class="structured-evidence-meta">{html.escape(meta or "Evidence")}</div>
        <div class="structured-evidence-quote">{quote}</div>
        {footer_html}
    </div>
    """


def _render_structured_value_html(value: object) -> str:
    """Render nested JSON values into readable HTML."""
    if _looks_like_evidence(value):
        return _render_evidence_html(value)

    if isinstance(value, dict):
        if not value:
            return '<div class="structured-empty">No data.</div>'
        fields = []
        for key, item in value.items():
            fields.append(
                f"""
                <div class="structured-field">
                    <div class="structured-label">{html.escape(_format_label(str(key)))}</div>
                    {_render_structured_value_html(item)}
                </div>
                """
            )
        return "".join(fields)

    if isinstance(value, list):
        if not value:
            return '<div class="structured-empty">No items.</div>'
        if all(_is_scalar(item) for item in value):
            chips = "".join(
                f'<span class="structured-chip">{html.escape(_scalar_text(item))}</span>'
                for item in value
            )
            return f'<div class="structured-chip-row">{chips}</div>'

        items = "".join(
            f'<div class="structured-list-item">{_render_structured_value_html(item)}</div>'
            for item in value
        )
        return f'<div class="structured-list">{items}</div>'

    return f'<div class="structured-text">{html.escape(_scalar_text(value)).replace(chr(10), "<br>")}</div>'


def _render_answer_body(answer: object) -> None:
    """Render plain text answers or structured JSON-like answers."""
    structured = _maybe_parse_structured_answer(answer)
    if structured is None:
        st.markdown(
            f"""
            <div class="result-card answer-card">
                <div class="card-body">{html.escape(_scalar_text(answer)).replace(chr(10), "<br>")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if isinstance(structured, dict):
        for key, value in structured.items():
            st.markdown(
                f"""
                <div class="result-card answer-card">
                    <div class="result-title">{html.escape(_format_label(str(key)))}</div>
                    {_render_structured_value_html(value)}
                </div>
                """,
                unsafe_allow_html=True,
            )
        return

    st.markdown(
        f"""
        <div class="result-card answer-card">
            <div class="result-title">Structured Answer</div>
            {_render_structured_value_html(structured)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_response(response: dict) -> None:
    """Render answer or refusal plus citations and retrieval context."""
    answer = response.get("answer")
    refusal_reason = response.get("refusal_reason")
    warning = response.get("_warning")
    citations = response.get("citations", [])

    confidence = str(response.get("confidence", "unknown")).upper()
    st.markdown(
        f'<div class="confidence-pill">Confidence: {html.escape(confidence)}</div>',
        unsafe_allow_html=True,
    )
    if confidence in CONFIDENCE_GUIDE:
        st.markdown(
            f"""
            <div class="confidence-copy">
                {html.escape(CONFIDENCE_GUIDE[confidence])}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if answer:
        _render_card("Answer ready", card_class="notice-success")
        if warning:
            _render_card("Weak evidence warning", warning, card_class="notice-warning")
        if refusal_reason:
            _render_card("Model caution", refusal_reason, card_class="notice-warning")
        _render_answer_body(answer)
    else:
        _render_card("System refused the question", card_class="notice-error")
        _render_card(refusal_reason or "No refusal reason provided.", card_class="answer-card")

    if citations:
        st.subheader("Citations")
        for i, citation in enumerate(citations, 1):
            render_citation(citation, i)

    retrieval = response.get("retrieval", [])
    if retrieval:
        with st.expander("Retrieved evidence", expanded=False):
            for item in retrieval:
                meta = " | ".join(
                    part
                    for part in (
                        item.get("ticker"),
                        item.get("filing_type"),
                        item.get("section_name"),
                    )
                    if part
                )
                st.markdown(f"**{meta or item.get('doc_name', 'Retrieved chunk')}**")
                if item.get("text_preview"):
                    _render_retrieval_preview(str(item["text_preview"]))


def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(
        page_title="SEC Filing Assistant",
        page_icon="chart_with_upwards_trend",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(20, 88, 79, 0.10), transparent 28%),
                linear-gradient(180deg, #fbfaf7 0%, #f2ece2 100%);
        }
        [data-testid="stAppViewContainer"] {
            color: #1a1c1d;
        }
        [data-testid="stSidebar"] {
            background: rgba(252, 250, 244, 0.96);
            border-right: 1px solid #ddd6c7;
        }
        [data-testid="stSidebar"] * {
            color: #1f2223 !important;
        }
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid #ddd6c7;
            border-radius: 20px;
            padding: 1rem 1.1rem;
            box-shadow: 0 14px 30px rgba(43, 37, 24, 0.08);
        }
        [data-testid="stMetric"] * {
            color: #1f2223 !important;
        }
        [data-testid="stForm"] {
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid #ddd6c7;
            border-radius: 24px;
            padding: 1rem 1rem 0.35rem 1rem;
            box-shadow: 0 18px 36px rgba(43, 37, 24, 0.08);
        }
        [data-testid="stTextArea"] textarea {
            background: #ffffff !important;
            color: #1a1c1d !important;
            border: 1px solid #d6cfbf !important;
            border-radius: 18px !important;
        }
        [data-testid="stTextArea"] textarea::placeholder {
            color: #6c6b67 !important;
        }
        .stButton > button,
        [data-testid="stFormSubmitButton"] > button {
            background: rgba(255, 255, 255, 0.96) !important;
            color: #1a1c1d !important;
            border: 1px solid #cfc6b5 !important;
            border-radius: 16px !important;
            min-height: 3.2rem;
            font-weight: 700;
            box-shadow: 0 8px 18px rgba(43, 37, 24, 0.06);
            transition: background-color 0.18s ease, border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
        }
        .stButton > button:hover,
        [data-testid="stFormSubmitButton"] > button:hover {
            background: #ffffff !important;
            color: #1a1c1d !important;
            border-color: #14584f !important;
            box-shadow: 0 12px 24px rgba(20, 88, 79, 0.10);
            transform: translateY(-1px);
        }
        .stButton > button:focus,
        [data-testid="stFormSubmitButton"] > button:focus {
            color: #1a1c1d !important;
            border-color: #14584f !important;
            box-shadow: 0 0 0 1px #14584f !important;
        }
        [data-testid="stExpander"] {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid #ddd6c7;
            border-radius: 20px;
        }
        [data-testid="stExpander"] details summary {
            background: #efe6d8 !important;
            border-radius: 16px !important;
            padding: 0.35rem 0.75rem !important;
            transition: background-color 0.18s ease, color 0.18s ease;
        }
        [data-testid="stExpander"] details summary:hover {
            background: #e4d8c4 !important;
        }
        [data-testid="stExpander"] details[open] summary {
            background: #14584f !important;
        }
        [data-testid="stExpander"] * {
            color: #1f2223 !important;
        }
        [data-testid="stExpander"] details[open] summary,
        [data-testid="stExpander"] details[open] summary * {
            color: #ffffff !important;
        }
        .hero-copy {
            padding: 0.25rem 0 1rem 0;
        }
        .hero-eyebrow {
            color: #14584f;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }
        .hero-title {
            color: #1e2522;
            font-size: 2.7rem;
            font-weight: 700;
            line-height: 1.05;
            margin: 0.35rem 0;
        }
        .hero-lead {
            color: #535a57;
            font-size: 1.02rem;
            line-height: 1.7;
            max-width: 52rem;
        }
        .helper-copy {
            color: #3c403e;
            font-size: 0.98rem;
            line-height: 1.6;
            margin: 0 0 1rem 0;
        }
        .top-stat-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin: 0.2rem 0 1rem 0;
        }
        .top-stat-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            flex-wrap: wrap;
            padding: 0.45rem 0.8rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid #ddd6c7;
            box-shadow: 0 10px 24px rgba(43, 37, 24, 0.06);
        }
        .top-stat-label {
            color: #6d726f;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .top-stat-value {
            color: #1f2223;
            font-size: 0.92rem;
            font-weight: 700;
            overflow-wrap: anywhere;
        }
        .top-stat-note {
            color: #6d726f;
            font-size: 0.83rem;
            line-height: 1.5;
            margin: -0.55rem 0 1rem 0.2rem;
        }
        .confidence-guide {
            background: rgba(255, 255, 255, 0.92);
            color: #1f2223;
            border: 1px solid #ddd6c7;
            border-radius: 18px;
            padding: 0.95rem 1rem;
            margin: 0.45rem 0 1.25rem 0;
            box-shadow: 0 14px 28px rgba(43, 37, 24, 0.08);
        }
        .confidence-guide strong {
            color: #1f2223;
        }
        .confidence-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.45rem 0.8rem;
            border-radius: 999px;
            background: rgba(20, 88, 79, 0.12);
            color: #14584f;
            border: 1px solid rgba(20, 88, 79, 0.18);
            font-size: 0.84rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            margin-bottom: 0.85rem;
        }
        .confidence-copy {
            color: #242424;
            font-size: 0.95rem;
            line-height: 1.6;
            margin: -0.2rem 0 0.8rem 0;
            max-width: 50rem;
        }
        .retrieval-preview {
            color: #252927;
            font-size: 0.98rem;
            line-height: 1.7;
            white-space: pre-wrap;
            word-break: break-word;
            margin: 0.35rem 0 1rem 0;
        }
        .result-card {
            background: rgba(255, 255, 255, 0.94);
            color: #1f2223;
            border: 1px solid #ddd6c7;
            border-radius: 20px;
            padding: 1rem 1.1rem;
            margin: 0.75rem 0;
            box-shadow: 0 14px 30px rgba(43, 37, 24, 0.08);
        }
        .result-title {
            color: #1f2223;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .card-body {
            color: #252927;
            font-size: 1.02rem;
            line-height: 1.7;
        }
        .result-meta {
            color: #6a6b67;
            font-size: 0.86rem;
            line-height: 1.5;
            margin-top: 0.6rem;
        }
        .citation-quote {
            color: #252927;
            font-size: 0.98rem;
            line-height: 1.7;
            border-left: 3px solid #14584f;
            padding-left: 0.8rem;
            margin-top: 0.45rem;
        }
        .structured-field + .structured-field {
            margin-top: 0.95rem;
        }
        .structured-label {
            color: #6d726f;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.4rem;
        }
        .structured-text {
            color: #252927;
            font-size: 1rem;
            line-height: 1.7;
        }
        .structured-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }
        .structured-chip {
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: #f6f1e7;
            border: 1px solid #d7cebe;
            color: #2a2d2b;
            font-size: 0.88rem;
            line-height: 1.2;
        }
        .structured-list {
            display: grid;
            gap: 0.75rem;
        }
        .structured-list-item {
            background: #fbfaf7;
            border: 1px solid #e2dbc9;
            border-radius: 16px;
            padding: 0.85rem 0.9rem;
        }
        .structured-evidence {
            background: #fbfaf7;
            border: 1px solid #e2dbc9;
            border-radius: 16px;
            padding: 0.85rem 0.9rem;
        }
        .structured-evidence-meta {
            color: #5e6561;
            font-size: 0.82rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }
        .structured-evidence-quote {
            color: #252927;
            font-size: 0.96rem;
            line-height: 1.65;
            border-left: 3px solid #14584f;
            padding-left: 0.75rem;
        }
        .structured-evidence-footer {
            color: #70726d;
            font-size: 0.84rem;
            margin-top: 0.55rem;
        }
        .structured-empty {
            color: #7b7e79;
            font-style: italic;
        }
        .notice-success {
            border-color: #1e8f59;
        }
        .notice-warning {
            border-color: #d1a100;
        }
        .notice-error {
            border-color: #cb4d4d;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="hero-copy">
            <div class="hero-eyebrow">SEC Filing Assistant</div>
            <div class="hero-title">SEC filing answers with visible evidence</div>
            <div class="hero-lead">
                Ask a question against the local filing corpus. The app calls the repo's pipeline directly,
                shows the answer or refusal, and renders citations in a reviewable format.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Quick prompts")
        st.write("These are shortcuts only. You can ask any filing-backed question in the main panel.")
        for label, question in EXAMPLE_QUESTIONS.items():
            if st.button(label, use_container_width=True):
                set_example(question)
        st.divider()
        st.write("Answers are generated from the local SEC filing corpus and include source citations.")

    store_path = PROJECT_ROOT / config.vector_store_path / "chunks.jsonl"
    if not store_path.exists():
        _render_card("No ingested corpus found", "Run `uv run python -m src.ingest` first.", "notice-warning")
        st.stop()

    try:
        chunks, index = load_runtime()
    except FileNotFoundError:
        _render_card("Vector store missing", "Re-run `uv run python -m src.ingest` before using the frontend.", "notice-error")
        st.stop()
    except Exception as exc:
        st.exception(exc)
        st.stop()

    _render_top_stat_pills(chunks)

    st.session_state.setdefault("question_input", EXAMPLE_QUESTIONS["Single-company"])
    st.session_state.setdefault("last_response", None)
    st.session_state.setdefault("last_question", None)

    st.markdown(
        """
        <div class="helper-copy">
            Use one of the quick prompts or type your own question. The app is not limited to single-company or
            cross-company demos; any filing-backed question is fair game.
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("question_form", clear_on_submit=False):
        question = st.text_area(
            "Question",
            key="question_input",
            height=120,
            placeholder="Ask anything backed by the filing corpus: revenue, risk factors, comparisons, segment results, or trend questions.",
        )
        submitted = st.form_submit_button("Submit question", use_container_width=True)

    st.markdown(
        """
        <div class="confidence-guide">
            <strong>Confidence guide</strong><br>
            High: directly stated in the filing text.<br>
            Medium: supported by the filings, but requires some synthesis.<br>
            Low: weak or incomplete evidence; an answer may still be shown, but treat it cautiously.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if submitted:
        trimmed = question.strip()
        if not trimmed:
            _render_card("Question required", "Enter a question before submitting.", "notice-warning")
        else:
            with st.spinner("Reading filings, retrieving evidence, and composing a cited answer..."):
                st.session_state["last_response"] = ask(trimmed, chunks=chunks, index=index)
                st.session_state["last_question"] = trimmed

    last_question = st.session_state.get("last_question")
    last_response = st.session_state.get("last_response")
    if last_question and last_response is not None:
        st.subheader("Result")
        st.caption(last_question)
        render_response(last_response)


if __name__ == "__main__":
    main()
