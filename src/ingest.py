"""Ingest — load documents, chunk, embed, store."""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

from src.config import config
from src.telemetry import traced_embedding

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A chunk of text with source metadata."""
    chunk_id: str
    text: str
    doc_name: str
    page: int | None = None
    section: str | None = None
    char_start: int = 0
    char_end: int = 0
    embedding: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("embedding")  # stored separately
        return d


def load_documents(data_dir: str | None = None) -> list[dict]:
    """
    Load all documents from data directory.

    Returns list of {"doc_name": str, "text": str, "pages": list[str] | None}.
    Supports: .txt, .md, .pdf (via pypdf).
    """
    data_dir = data_dir or config.data_dir
    docs = []

    for path in sorted(Path(data_dir).glob("*")):
        if path.suffix.lower() == ".pdf":
            docs.append(_load_pdf(path))
        elif path.suffix.lower() in (".txt", ".md"):
            docs.append({
                "doc_name": path.name,
                "text": path.read_text(encoding="utf-8"),
                "pages": None,
            })
        else:
            logger.debug(f"Skipping unsupported file: {path.name}")

    logger.info(f"Loaded {len(docs)} documents from {data_dir}")
    return docs


def _load_pdf(path: Path) -> dict:
    """Load PDF with page-level text extraction."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("Install pypdf: pip install pypdf")

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)

    return {
        "doc_name": path.name,
        "text": "\n\n".join(pages),
        "pages": pages,
    }


def chunk_document(doc: dict, chunk_size: int | None = None, overlap: int | None = None) -> list[Chunk]:
    """
    Chunk a document into overlapping text segments with metadata.

    Override this function for corpus-specific chunking (e.g., by section headers).
    Default: sliding window with overlap.
    """
    chunk_size = chunk_size or config.chunk_size
    overlap = overlap or config.chunk_overlap
    doc_name = doc["doc_name"]
    text = doc["text"]
    pages = doc.get("pages")

    chunks = []
    start = 0
    chunk_idx = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Try to break at sentence boundary
        if end < len(text):
            last_period = text.rfind(".", start, end)
            if last_period > start + chunk_size // 2:
                end = last_period + 1

        chunk_text = text[start:end].strip()
        if chunk_text:
            page_num = _find_page(start, pages) if pages else None
            chunks.append(Chunk(
                chunk_id=f"{doc_name}::{chunk_idx}",
                text=chunk_text,
                doc_name=doc_name,
                page=page_num,
                char_start=start,
                char_end=end,
            ))
            chunk_idx += 1

        start = end - overlap if end < len(text) else end

    logger.info(f"Chunked {doc_name}: {len(chunks)} chunks")
    return chunks


def _find_page(char_offset: int, pages: list[str]) -> int | None:
    """Map character offset to page number."""
    running = 0
    for i, page_text in enumerate(pages):
        running += len(page_text) + 2  # +2 for \n\n join
        if char_offset < running:
            return i + 1  # 1-indexed
    return len(pages)


def embed_chunks(chunks: list[Chunk], batch_size: int = 50) -> list[Chunk]:
    """Add embeddings to chunks in batches."""
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        embeddings = traced_embedding(texts, label=f"embed_batch_{i}")
        for chunk, emb in zip(batch, embeddings):
            chunk.embedding = emb

    logger.info(f"Embedded {len(chunks)} chunks")
    return chunks


def save_chunks(chunks: list[Chunk], store_path: str | None = None) -> None:
    """Persist chunks + embeddings to disk (JSON lines)."""
    store_path = store_path or config.vector_store_path
    os.makedirs(store_path, exist_ok=True)

    meta_path = os.path.join(store_path, "chunks.jsonl")
    emb_path = os.path.join(store_path, "embeddings.jsonl")

    with open(meta_path, "w") as mf, open(emb_path, "w") as ef:
        for chunk in chunks:
            mf.write(json.dumps(chunk.to_dict()) + "\n")
            ef.write(json.dumps({"chunk_id": chunk.chunk_id, "embedding": chunk.embedding}) + "\n")

    logger.info(f"Saved {len(chunks)} chunks to {store_path}")


def load_chunks(store_path: str | None = None) -> list[Chunk]:
    """Load chunks + embeddings from disk."""
    store_path = store_path or config.vector_store_path
    meta_path = os.path.join(store_path, "chunks.jsonl")
    emb_path = os.path.join(store_path, "embeddings.jsonl")

    chunks_by_id: dict[str, Chunk] = {}
    with open(meta_path) as f:
        for line in f:
            d = json.loads(line)
            chunks_by_id[d["chunk_id"]] = Chunk(**d)

    with open(emb_path) as f:
        for line in f:
            d = json.loads(line)
            if d["chunk_id"] in chunks_by_id:
                chunks_by_id[d["chunk_id"]].embedding = d["embedding"]

    chunks = list(chunks_by_id.values())
    logger.info(f"Loaded {len(chunks)} chunks from {store_path}")
    return chunks


def run_ingestion(data_dir: str | None = None) -> list[Chunk]:
    """Full ingestion pipeline: load → chunk → embed → save."""
    docs = load_documents(data_dir)
    all_chunks: list[Chunk] = []
    for doc in docs:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)

    all_chunks = embed_chunks(all_chunks)
    save_chunks(all_chunks)
    return all_chunks


if __name__ == "__main__":
    logging.basicConfig(level=config.log_level)
    chunks = run_ingestion()
    print(f"Ingested {len(chunks)} chunks from {config.data_dir}")
