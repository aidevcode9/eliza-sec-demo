"""Ingest — load SEC filings, parse metadata, strip XBRL, chunk by section, embed, persist."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.config import config
from src.telemetry import traced_embedding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 60

# Regex for Item headers at start of line (not TOC lines with | separators).
# Matches: "Item 1.", "Item 1A.", "ITEM 7A.", "Item 9C.", etc.
ITEM_HEADER_RE = re.compile(
    r"^(Item|ITEM)\s+(\d+[A-C]?)\.?\s",
    re.MULTILINE,
)

# Filename patterns
# With quarter:  AAPL_10K_2024Q3_2024-11-01_full.txt
# Without:       ABBV_10K_2025-02-14_full.txt
FILENAME_WITH_Q_RE = re.compile(
    r"^([A-Z]+)_(10[KQ])_(\d{4}Q\d)_(\d{4}-\d{2}-\d{2})_full\.txt$"
)
FILENAME_NO_Q_RE = re.compile(
    r"^([A-Z]+)_(10[KQ])_(\d{4}-\d{2}-\d{2})_full\.txt$"
)

# Filing type normalization: "10K" -> "10-K", "10Q" -> "10-Q"
FILING_TYPE_MAP = {"10K": "10-K", "10Q": "10-Q"}


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A chunk of SEC filing text with full source metadata."""

    chunk_id: str
    text: str
    doc_name: str
    ticker: str
    company: str
    filing_type: str
    filing_date: str
    section_name: str
    quarter: str | None = None
    report_period: str | None = None
    char_start: int = 0
    char_end: int = 0
    embedding: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, excluding embedding (stored separately)."""
        d = asdict(self)
        d.pop("embedding")
        return d


# ---------------------------------------------------------------------------
# Metadata parsing
# ---------------------------------------------------------------------------

def parse_metadata(lines: list[str]) -> dict[str, Any]:
    """
    Parse key-value metadata header from filing lines.

    Reads lines until the separator (====...) is found.
    Normalizes filing_type from "10-K (Annual Report)" -> "10-K".
    """
    meta: dict[str, Any] = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("="):
            break
        if ": " not in stripped:
            continue

        key, value = stripped.split(": ", 1)
        key_lower = key.strip().lower().replace(" ", "_")
        meta[key_lower] = value.strip()

    # Normalize filing_type: "10-K (Annual Report)" -> "10-K"
    if "filing_type" in meta:
        ft = meta["filing_type"]
        paren_idx = ft.find("(")
        if paren_idx > 0:
            meta["filing_type"] = ft[:paren_idx].strip()

    # Ensure optional fields are explicitly None if missing
    for optional in ("report_period", "quarter"):
        if optional not in meta:
            meta[optional] = None

    return meta


def parse_filename(filename: str) -> dict[str, Any]:
    """
    Extract ticker, filing_type, quarter, filing_date from filename.

    Supports two patterns:
      - AAPL_10K_2024Q3_2024-11-01_full.txt (with quarter)
      - ABBV_10K_2025-02-14_full.txt (without quarter)
    """
    m = FILENAME_WITH_Q_RE.match(filename)
    if m:
        return {
            "ticker": m.group(1),
            "filing_type": FILING_TYPE_MAP.get(m.group(2), m.group(2)),
            "quarter": m.group(3),
            "filing_date": m.group(4),
        }

    m = FILENAME_NO_Q_RE.match(filename)
    if m:
        return {
            "ticker": m.group(1),
            "filing_type": FILING_TYPE_MAP.get(m.group(2), m.group(2)),
            "quarter": None,
            "filing_date": m.group(3),
        }

    logger.warning("Could not parse filename: %s", filename)
    return {"ticker": "", "filing_type": "", "quarter": None, "filing_date": ""}


# ---------------------------------------------------------------------------
# XBRL stripping
# ---------------------------------------------------------------------------

def strip_xbrl(lines: list[str]) -> list[str]:
    """
    Strip XBRL / noisy leading text.

    Finds the first line containing "UNITED STATES" and returns
    everything from that line onward.
    """
    for i, line in enumerate(lines):
        if "UNITED STATES" in line:
            return lines[i:]

    logger.warning("No 'UNITED STATES' marker found; returning all lines")
    return lines


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def _is_toc_line(line: str) -> bool:
    """Return True if line looks like a Table of Contents entry (has | separator)."""
    return "|" in line


def _normalize_section_name(match_text: str) -> str:
    """
    Normalize 'Item 1A.' or 'ITEM 1A.' -> 'Item 1A'.
    """
    # Extract the item number part
    m = re.match(r"(?:Item|ITEM)\s+(\d+[A-C]?)", match_text)
    if m:
        return f"Item {m.group(1)}"
    return match_text.strip().rstrip(".")


def split_sections(text: str, filing_type: str) -> list[dict[str, Any]]:
    """
    Split filing text into sections by Item headers.

    Skips TOC lines (contain | and page numbers).
    For 10-Q, tracks current Part (I/II) for namespacing.
    Returns list of {"section_name": str, "text": str, "char_start": int, "char_end": int}.
    """
    # Pre-normalize: insert newlines before Item headers that appear mid-line.
    # SEC .txt files often have sections concatenated on single long lines
    # with patterns like "35Table of ContentsItem 7." or "applicable.Item 1B."
    # Break before Item headers that follow:
    #   - a digit (page number): "35Item 7."
    #   - "Table of Contents": "Table of ContentsItem 7."
    #   - a period: "applicable.Item 1B."
    #   - "Part I" or "Part II": "Part IItem 1."
    text = re.sub(r"(\d)((?:Item|ITEM)\s*\d+[A-C]?\.?\s)", r"\1\n\2", text)
    text = re.sub(r"(Table of Contents)((?:Item|ITEM)\s*\d+[A-C]?\.?\s)", r"\1\n\2", text)
    text = re.sub(r"(\.)(?=(?:Item|ITEM)\s*\d+[A-C]?\.?\s)", r".\n", text)
    # Also insert newlines before Part headers mid-line
    text = re.sub(r"(?<=\S)((?:PART|Part)\s+(?:I{1,2}|[12])\b)", r"\n\1", text)
    lines = text.split("\n")
    sections: list[dict[str, Any]] = []
    current_part: str = ""
    current_section: str | None = None
    section_lines: list[str] = []
    section_start: int = 0
    char_pos: int = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for the newline we split on

        # Track Part headers for 10-Q
        part_match = re.match(r"^\s*(?:PART|Part)\s+(I{1,2}|[12])\b", line)
        if part_match:
            part_num = part_match.group(1)
            # Normalize: "1" -> "I", "2" -> "II"
            if part_num == "1":
                part_num = "I"
            elif part_num == "2":
                part_num = "II"
            current_part = f"Part {part_num}"

        # Check for Item header
        item_match = ITEM_HEADER_RE.match(line.strip())
        if item_match and not _is_toc_line(line):
            # Save previous section
            if current_section is not None and section_lines:
                section_text = "\n".join(section_lines).strip()
                if section_text:
                    sections.append({
                        "section_name": current_section,
                        "text": section_text,
                        "char_start": section_start,
                        "char_end": char_pos,
                    })

            # Start new section
            raw_name = _normalize_section_name(item_match.group(0))
            if filing_type == "10-Q" and current_part:
                current_section = f"{current_part} - {raw_name}"
            else:
                current_section = raw_name
            section_lines = [line.strip()]
            section_start = char_pos
        elif current_section is not None:
            # Skip TOC lines but accumulate real content
            if not _is_toc_line(line):
                section_lines.append(line)

        char_pos += line_len

    # Flush last section
    if current_section is not None and section_lines:
        section_text = "\n".join(section_lines).strip()
        if section_text:
            sections.append({
                "section_name": current_section,
                "text": section_text,
                "char_start": section_start,
                "char_end": char_pos,
            })

    return sections


# ---------------------------------------------------------------------------
# Sub-chunking
# ---------------------------------------------------------------------------

def sub_chunk(text: str, max_size: int = 2000, overlap: int = 200) -> list[str]:
    """
    Split text into overlapping chunks for sections exceeding max_size.

    Tries to break at sentence boundaries (period followed by space).
    Returns original text as single-element list if within max_size.
    """
    if len(text) <= max_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + max_size, len(text))

        # Try to break at sentence boundary
        if end < len(text):
            # Look for last ". " in the chunk
            last_period = text.rfind(". ", start + max_size // 2, end)
            if last_period > 0:
                end = last_period + 1  # include the period

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(chunk_text)

        if end >= len(text):
            break

        start = end - overlap

    return chunks


# ---------------------------------------------------------------------------
# Document-level orchestration
# ---------------------------------------------------------------------------

def chunk_document(filepath: Path) -> list[Chunk]:
    """
    Process a single SEC filing: parse metadata, strip XBRL, split sections, sub-chunk.

    Returns list of Chunk objects (without embeddings).
    """
    raw_text = filepath.read_text(encoding="utf-8", errors="replace")
    all_lines = raw_text.split("\n")

    # 1. Parse metadata from header
    header_meta = parse_metadata(all_lines)

    # 2. Parse metadata from filename (as cross-check / fallback)
    file_meta = parse_filename(filepath.name)

    # Merge: prefer header, fallback to filename
    ticker = header_meta.get("ticker", file_meta.get("ticker", ""))
    company = header_meta.get("company", "")
    filing_type = header_meta.get("filing_type", file_meta.get("filing_type", ""))
    filing_date = header_meta.get("filing_date", file_meta.get("filing_date", ""))
    quarter = header_meta.get("quarter") or file_meta.get("quarter")
    report_period = header_meta.get("report_period")

    # 3. Find content after separator, then strip XBRL
    separator_idx = 0
    for i, line in enumerate(all_lines):
        if line.strip().startswith("=" * 20):
            separator_idx = i + 1
            break

    content_lines = strip_xbrl(all_lines[separator_idx:])
    content_text = "\n".join(content_lines)

    # 4. Split into sections
    sections = split_sections(content_text, filing_type)

    # If no sections found, treat entire content as one chunk
    if not sections:
        sections = [{
            "section_name": "Full Document",
            "text": content_text,
            "char_start": 0,
            "char_end": len(content_text),
        }]

    # 5. Sub-chunk each section and create Chunk objects
    chunks: list[Chunk] = []
    chunk_idx = 0

    for section in sections:
        section_text = section["text"]
        section_name = section["section_name"]

        sub_texts = sub_chunk(section_text, max_size=config.chunk_size, overlap=config.chunk_overlap)

        for sub_text in sub_texts:
            # Calculate char positions within the section
            local_start = section_text.find(sub_text[:50]) if sub_text else 0
            if local_start < 0:
                local_start = 0

            chunks.append(Chunk(
                chunk_id=f"{filepath.name}::{chunk_idx}",
                text=sub_text,
                doc_name=filepath.name,
                ticker=ticker,
                company=company,
                filing_type=filing_type,
                filing_date=filing_date,
                section_name=section_name,
                quarter=quarter,
                report_period=report_period,
                char_start=section["char_start"] + local_start,
                char_end=section["char_start"] + local_start + len(sub_text),
            ))
            chunk_idx += 1

    logger.info("Chunked %s: %d sections, %d chunks", filepath.name, len(sections), len(chunks))
    return chunks


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_chunks(chunks: list[Chunk], batch_size: int = 50) -> list[Chunk]:
    """Add embeddings to chunks in batches via traced_embedding()."""
    total = len(chunks)
    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        embeddings = traced_embedding(texts, label=f"embed_batch_{i // batch_size}")
        for chunk, emb in zip(batch, embeddings):
            chunk.embedding = emb
        logger.info("Embedded batch %d/%d", i // batch_size + 1, (total + batch_size - 1) // batch_size)

    logger.info("Embedded %d chunks total", total)
    return chunks


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_chunks(chunks: list[Chunk], store_path: str | None = None) -> None:
    """Persist chunks + embeddings to disk as JSON lines."""
    store_path = store_path or config.vector_store_path
    os.makedirs(store_path, exist_ok=True)

    meta_path = os.path.join(store_path, "chunks.jsonl")
    emb_path = os.path.join(store_path, "embeddings.jsonl")

    with open(meta_path, "w", encoding="utf-8") as mf, \
         open(emb_path, "w", encoding="utf-8") as ef:
        for chunk in chunks:
            mf.write(json.dumps(chunk.to_dict()) + "\n")
            ef.write(json.dumps({"chunk_id": chunk.chunk_id, "embedding": chunk.embedding}) + "\n")

    logger.info("Saved %d chunks to %s", len(chunks), store_path)


def load_chunks(store_path: str | None = None) -> list[Chunk]:
    """Load chunks + embeddings from disk."""
    store_path = store_path or config.vector_store_path
    meta_path = os.path.join(store_path, "chunks.jsonl")
    emb_path = os.path.join(store_path, "embeddings.jsonl")

    chunks_by_id: dict[str, Chunk] = {}
    with open(meta_path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            chunks_by_id[d["chunk_id"]] = Chunk(**d)

    if os.path.exists(emb_path):
        with open(emb_path, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                if d["chunk_id"] in chunks_by_id:
                    chunks_by_id[d["chunk_id"]].embedding = d["embedding"]

    chunks = list(chunks_by_id.values())
    logger.info("Loaded %d chunks from %s", len(chunks), store_path)
    return chunks


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_ingestion(data_dir: str | None = None) -> list[Chunk]:
    """
    Full ingestion pipeline: discover files -> chunk each -> embed -> save.

    Logs total chunks and elapsed time.
    """
    data_dir = data_dir or config.data_dir
    start_time = time.time()

    # Discover .txt files
    txt_files = sorted(Path(data_dir).glob("*.txt"))
    logger.info("Found %d .txt files in %s", len(txt_files), data_dir)

    if not txt_files:
        logger.warning("No .txt files found in %s", data_dir)
        return []

    # Chunk all documents
    all_chunks: list[Chunk] = []
    for filepath in txt_files:
        try:
            chunks = chunk_document(filepath)
            all_chunks.extend(chunks)
        except Exception:
            logger.exception("Failed to process %s", filepath.name)

    logger.info("Total chunks before embedding: %d", len(all_chunks))

    # Embed
    all_chunks = embed_chunks(all_chunks)

    # Save
    save_chunks(all_chunks)

    elapsed = time.time() - start_time
    logger.info(
        "Ingestion complete: %d files, %d chunks, %.1f seconds",
        len(txt_files),
        len(all_chunks),
        elapsed,
    )
    return all_chunks


if __name__ == "__main__":
    logging.basicConfig(level=config.log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    chunks = run_ingestion()
    logger.info("Ingested %d chunks from %s", len(chunks), config.data_dir)
