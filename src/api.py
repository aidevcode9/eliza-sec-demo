"""API — FastAPI endpoints for the RAG assignment."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from src.config import config
from src.ingest import Chunk, load_chunks
from src.pipeline import ask
from src.retrieve import RetrievalIndex
from src.telemetry import get_call_log, shutdown_telemetry

logging.basicConfig(level=config.log_level)
logger = logging.getLogger(__name__)

# Load chunks + precompute retrieval index once at startup
_chunks: list[Chunk] = []
_index: RetrievalIndex | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load chunks + build index. Shutdown: flush telemetry."""
    global _chunks, _index
    try:
        _chunks = load_chunks()
        _index = RetrievalIndex(_chunks)
        logger.info("Loaded %d chunks, built retrieval index at startup", len(_chunks))
    except FileNotFoundError:
        logger.warning("No vector store found. Run `python -m src.ingest` first.")
    yield
    shutdown_telemetry()


app = FastAPI(title="RAG Assignment", version="0.1.0", lifespan=lifespan)


class QuestionRequest(BaseModel):
    question: str


@app.get("/healthz")
def health():
    status = "ok" if _chunks else "degraded"
    return {"status": status, "chunks_loaded": len(_chunks)}


@app.post("/v1/ask")
def ask_question(req: QuestionRequest):
    """Ask a question against the corpus."""
    response = ask(req.question, chunks=_chunks, index=_index)
    return response


@app.get("/v1/telemetry")
def telemetry():
    """Return LLM call log for this session."""
    return {"calls": get_call_log()}
