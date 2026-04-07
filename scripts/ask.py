"""Interactive Q&A — ask questions against the ingested corpus.

Usage:
    uv run python scripts/ask.py                    # interactive mode
    uv run python scripts/ask.py "What was NVIDIA's revenue?"  # single question
    uv run python scripts/ask.py --ingest-first     # ingest then ask
    uv run python scripts/ask.py --ingest-only      # just ingest, don't ask
    uv run python scripts/ask.py --quick-ingest     # ingest 6 eval companies only
"""

import json
import logging
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config  # noqa: E402

logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Eval-priority companies for quick ingest
QUICK_TICKERS = {"NVDA", "AAPL", "TSLA", "JPM", "PFE", "AMZN"}


def quick_ingest() -> None:
    """Ingest only the 6 eval-priority companies."""
    from src.ingest import chunk_document, embed_chunks, save_chunks

    data_dir = Path(config.data_dir)
    files = [
        f for f in sorted(data_dir.glob("*.txt"))
        if any(f.name.startswith(t + "_") for t in QUICK_TICKERS)
    ]
    logger.info("Quick ingest: %d files from %s", len(files), QUICK_TICKERS)

    all_chunks = []
    for filepath in files:
        chunks = chunk_document(filepath)
        all_chunks.extend(chunks)
        logger.info("  %s → %d chunks", filepath.name, len(chunks))

    logger.info("Embedding %d chunks...", len(all_chunks))
    all_chunks = embed_chunks(all_chunks)
    save_chunks(all_chunks)
    logger.info("Done! %d chunks saved to %s", len(all_chunks), config.vector_store_path)


def full_ingest() -> None:
    """Ingest the full corpus."""
    from src.ingest import run_ingestion
    run_ingestion()


def ask_question(question: str) -> None:
    """Ask a single question and print the result."""
    from src.pipeline import ask

    print(f"\n{'='*60}")
    print(f"Q: {question}")
    print(f"{'='*60}\n")

    response = ask(question)

    if response.get("answer"):
        print(f"A: {response['answer']}\n")
        print(f"Confidence: {response.get('confidence', '?')}")
        if response.get("citations"):
            print(f"\nCitations ({len(response['citations'])}):")
            for i, c in enumerate(response["citations"], 1):
                ticker = c.get("ticker", "?")
                filing = c.get("filing_type", "?")
                date = c.get("filing_date", "?")
                section = c.get("section", "?")
                quote = c.get("quoted_text", "")[:100]
                print(f"  [{i}] {ticker} {filing} {date}, {section}")
                if quote:
                    print(f"      \"{quote}...\"")
    else:
        print(f"REFUSED: {response.get('refusal_reason', 'Unknown reason')}")

    if response.get("retrieval"):
        print(f"\nRetrieved {len(response['retrieval'])} chunks:")
        for r in response["retrieval"][:3]:
            print(f"  - {r.get('ticker', '?')} {r.get('filing_type', '?')} "
                  f"{r.get('section_name', '?')} (score: {r.get('score', '?')})")

    print()


def interactive_loop() -> None:
    """Interactive question loop."""
    print("\n" + "="*60)
    print("SEC Filing RAG — Interactive Q&A")
    print("="*60)
    print("Type a question and press Enter. Type 'quit' to exit.\n")

    # Sample questions
    print("Sample questions:")
    print("  1. What was NVIDIA's total revenue for fiscal year 2025?")
    print("  2. How much revenue did AWS generate in 2024?")
    print("  3. Compare Apple and Pfizer risk factors.")
    print("  4. What is the current stock price of NVIDIA? (should refuse)")
    print()

    while True:
        try:
            question = input("Q: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not question or question.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        # Shortcut: number picks a sample question
        samples = {
            "1": "What was NVIDIA's total revenue for fiscal year 2025?",
            "2": "How much revenue did Amazon Web Services (AWS) generate in 2024?",
            "3": "Compare the risk factors of Apple and Pfizer.",
            "4": "What is the current stock price of NVIDIA?",
        }
        question = samples.get(question, question)

        ask_question(question)


def main() -> None:
    args = sys.argv[1:]

    if not config.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set. Add it to .env or src/.env")
        sys.exit(1)

    if "--ingest-only" in args:
        full_ingest()
        return

    if "--quick-ingest" in args:
        quick_ingest()
        return

    if "--ingest-first" in args:
        full_ingest()
        args.remove("--ingest-first")

    # Check if corpus is ingested
    store = Path(config.vector_store_path)
    if not (store / "chunks.jsonl").exists():
        print("No ingested corpus found. Run one of:")
        print("  uv run python scripts/ask.py --quick-ingest   # 6 companies (~5 min)")
        print("  uv run python scripts/ask.py --ingest-only    # full corpus (~30 min)")
        sys.exit(1)

    # Single question from CLI arg
    remaining = [a for a in args if not a.startswith("--")]
    if remaining:
        ask_question(" ".join(remaining))
    else:
        interactive_loop()


if __name__ == "__main__":
    main()
