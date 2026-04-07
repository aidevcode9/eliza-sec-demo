"""Tests for SEC filing ingestion pipeline."""

from pathlib import Path

from src.ingest import (
    Chunk,
    load_chunks,
    parse_filename,
    parse_metadata,
    save_chunks,
    split_sections,
    strip_xbrl,
    sub_chunk,
)

# ---------------------------------------------------------------------------
# Metadata parsing
# ---------------------------------------------------------------------------

class TestParseMetadata:
    def test_parse_metadata_header_8_field(self, metadata_header_8_field: list[str]) -> None:
        """Older format with Quarter and Report Period."""
        meta = parse_metadata(metadata_header_8_field)
        assert meta["company"] == "Apple Inc"
        assert meta["ticker"] == "AAPL"
        assert meta["filing_type"] == "10-K"
        assert meta["filing_date"] == "2024-11-01"
        assert meta["report_period"] == "2024-09-28"
        assert meta["quarter"] == "2024Q3"
        assert meta["cik"] == "0000320193"

    def test_parse_metadata_header_6_field(self, metadata_header_6_field: list[str]) -> None:
        """Newer format without Quarter / Report Period."""
        meta = parse_metadata(metadata_header_6_field)
        assert meta["company"] == "AbbVie Inc"
        assert meta["ticker"] == "ABBV"
        assert meta["filing_type"] == "10-K"
        assert meta["filing_date"] == "2025-02-14"
        assert meta.get("report_period") is None
        assert meta.get("quarter") is None


# ---------------------------------------------------------------------------
# XBRL stripping
# ---------------------------------------------------------------------------

class TestStripXbrl:
    def test_strip_xbrl(self, xbrl_short: list[str]) -> None:
        """Content before 'UNITED STATES' is removed."""
        result = strip_xbrl(xbrl_short)
        assert result[0].startswith("UNITED STATES")
        assert len(result) == 4
        assert "xbrl" not in result[0].lower()

    def test_strip_xbrl_long_block(self, xbrl_long: list[str]) -> None:
        """Handles 1800+ line XBRL block."""
        result = strip_xbrl(xbrl_long)
        assert result[0].startswith("UNITED STATES")
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

class TestParseFilename:
    def test_parse_filename_with_quarter(self) -> None:
        """Pattern: AAPL_10K_2024Q3_2024-11-01_full.txt"""
        meta = parse_filename("AAPL_10K_2024Q3_2024-11-01_full.txt")
        assert meta["ticker"] == "AAPL"
        assert meta["filing_type"] == "10-K"
        assert meta["quarter"] == "2024Q3"
        assert meta["filing_date"] == "2024-11-01"

    def test_parse_filename_without_quarter(self) -> None:
        """Pattern: ABBV_10K_2025-02-14_full.txt"""
        meta = parse_filename("ABBV_10K_2025-02-14_full.txt")
        assert meta["ticker"] == "ABBV"
        assert meta["filing_type"] == "10-K"
        assert meta.get("quarter") is None
        assert meta["filing_date"] == "2025-02-14"


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

class TestSplitSections:
    def test_split_sections_10k(self, filing_10k_text: str) -> None:
        """Splits on Item headers, skips TOC lines (with | and page numbers)."""
        sections = split_sections(filing_10k_text, "10-K")
        section_names = [s["section_name"] for s in sections]
        assert "Item 1" in section_names
        assert "Item 1A" in section_names
        assert "Item 7" in section_names
        # Each section has text content
        for s in sections:
            assert len(s["text"].strip()) > 0

    def test_split_sections_10q(self, filing_10q_text: str) -> None:
        """Handles Part I / Part II namespacing for 10-Q."""
        sections = split_sections(filing_10q_text, "10-Q")
        section_names = [s["section_name"] for s in sections]
        # 10-Q has Part-namespaced items
        assert any("Item 1" in name for name in section_names)
        assert any("Item 1A" in name for name in section_names)
        assert len(sections) >= 3


# ---------------------------------------------------------------------------
# Sub-chunking
# ---------------------------------------------------------------------------

class TestSubChunk:
    def test_sub_chunk_large_section(self, large_section_text: str) -> None:
        """Sections > 2000 chars split with overlap."""
        assert len(large_section_text) > 2000
        chunks = sub_chunk(large_section_text, max_size=2000, overlap=200)
        assert len(chunks) >= 2
        # Each chunk <= max_size
        for c in chunks:
            assert len(c) <= 2000
        # Overlap: end of chunk N overlaps start of chunk N+1
        if len(chunks) >= 2:
            end_of_first = chunks[0][-100:]
            assert end_of_first in chunks[1]

    def test_chunk_preserves_metadata(self, large_section_text: str) -> None:
        """Sub-chunks carry parent section's metadata (tested via Chunk creation)."""
        texts = sub_chunk(large_section_text, max_size=2000, overlap=200)
        parent_meta = {
            "doc_name": "AAPL_10K_2024Q3_2024-11-01_full.txt",
            "ticker": "AAPL",
            "company": "Apple Inc",
            "filing_type": "10-K",
            "filing_date": "2024-11-01",
            "section_name": "Item 1A",
        }
        chunks = [
            Chunk(
                chunk_id=f"test::{i}",
                text=t,
                char_start=0,
                char_end=len(t),
                **parent_meta,
            )
            for i, t in enumerate(texts)
        ]
        assert len(chunks) >= 2
        for c in chunks:
            assert c.ticker == "AAPL"
            assert c.section_name == "Item 1A"
            assert c.filing_type == "10-K"


# ---------------------------------------------------------------------------
# Persistence round-trip
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Chunks survive save/load cycle."""
        chunks = [
            Chunk(
                chunk_id="test::0",
                text="Hello world",
                doc_name="TEST_10K_2024-01-01_full.txt",
                ticker="TEST",
                company="Test Corp",
                filing_type="10-K",
                filing_date="2024-01-01",
                section_name="Item 1",
                char_start=0,
                char_end=11,
                embedding=[0.1, 0.2, 0.3],
            )
        ]
        save_chunks(chunks, store_path=str(tmp_path))
        loaded = load_chunks(store_path=str(tmp_path))
        assert len(loaded) == 1
        assert loaded[0].chunk_id == "test::0"
        assert loaded[0].text == "Hello world"
        assert loaded[0].ticker == "TEST"
        assert loaded[0].embedding == [0.1, 0.2, 0.3]
