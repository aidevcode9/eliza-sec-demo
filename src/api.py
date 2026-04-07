"""API — FastAPI endpoints for the RAG assignment."""

import logging

from fastapi import FastAPI
from pydantic import BaseModel

from src.config import config
from src.ingest import Chunk, load_chunks
from src.pipeline import ask
from src.telemetry import get_call_log

logging.basicConfig(level=config.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="RAG Assignment", version="0.1.0")

# Load chunks once at startup
_chunks: list[Chunk] = []


@app.on_event("startup")
async def startup():
    global _chunks
    try:
        _chunks = load_chunks()
        logger.info(f"Loaded {len(_chunks)} chunks at startup")
    except FileNotFoundError:
        logger.warning("No vector store found. Run `python src/ingest.py` first.")


class QuestionRequest(BaseModel):
    question: str


@app.get("/healthz")
def health():
    return {"status": "ok", "chunks_loaded": len(_chunks)}


@app.post("/v1/ask")
def ask_question(req: QuestionRequest):
    """Ask a question against the corpus."""
    response = ask(req.question, chunks=_chunks)
    return response


@app.get("/v1/telemetry")
def telemetry():
    """Return LLM call log for this session."""
    return {"calls": get_call_log()}
