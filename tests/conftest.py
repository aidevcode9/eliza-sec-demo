"""Fixtures for ingest tests — small fake filing snippets."""

import pytest

SEPARATOR = "=" * 60


@pytest.fixture
def metadata_header_8_field() -> list[str]:
    """Older format: 8 key-value fields + separator."""
    return [
        "Company: Apple Inc",
        "Ticker: AAPL",
        "Filing Type: 10-K (Annual Report)",
        "Filing Date: 2024-11-01",
        "Report Period: 2024-09-28",
        "Quarter: 2024Q3",
        "CIK: 0000320193",
        "Source: SEC EDGAR",
        "URL: https://www.sec.gov/Archives/edgar/data/320193/filing.htm",
        SEPARATOR,
    ]


@pytest.fixture
def metadata_header_6_field() -> list[str]:
    """Newer format: 6 key-value fields, no Report Period / Quarter."""
    return [
        "Company: AbbVie Inc",
        "Ticker: ABBV",
        "Filing Type: 10-K (Annual Report)",
        "Filing Date: 2025-02-14",
        "CIK: 0001551152",
        "Source: SEC EDGAR",
        "URL: https://www.sec.gov/Archives/edgar/data/1551152/filing.htm",
        SEPARATOR,
    ]


@pytest.fixture
def xbrl_short() -> list[str]:
    """Short XBRL block followed by filing content."""
    return [
        "xbrl-data-line-1-fasb-stuff",
        "xbrl-data-line-2-more-fasb",
        "UNITED STATES",
        "SECURITIES AND EXCHANGE COMMISSION",
        "Washington, D.C. 20549",
        "FORM 10-K",
    ]


@pytest.fixture
def xbrl_long() -> list[str]:
    """Long XBRL block (1800+ lines) followed by filing content."""
    xbrl_lines = [f"xbrl-data-line-{i}" for i in range(1850)]
    filing_lines = [
        "UNITED STATES",
        "SECURITIES AND EXCHANGE COMMISSION",
        "Washington, D.C. 20549",
    ]
    return xbrl_lines + filing_lines


@pytest.fixture
def filing_10k_text() -> str:
    """Fake 10-K body with Item section headers."""
    return (
        "UNITED STATES\n"
        "SECURITIES AND EXCHANGE COMMISSION\n"
        "FORM 10-K\n"
        "Table of Contents\n"
        "Item 1. | Business | 1\n"
        "Item 1A. | Risk Factors | 5\n"
        "Item 7. | MD&A | 21\n"
        "\n"
        "Item 1.    Business\n"
        "Apple designs and sells consumer electronics. "
        "The Company also offers services.\n"
        "\n"
        "Item 1A.    Risk Factors\n"
        "Global economic conditions could materially adversely affect the Company. "
        "Foreign exchange risk is significant.\n"
        "\n"
        "Item 7.    Management's Discussion and Analysis\n"
        "Revenue increased 5% year over year driven by Services growth.\n"
    )


@pytest.fixture
def filing_10q_text() -> str:
    """Fake 10-Q body with Part I / Part II namespaced Items."""
    return (
        "UNITED STATES\n"
        "SECURITIES AND EXCHANGE COMMISSION\n"
        "FORM 10-Q\n"
        "Table of Contents\n"
        "Part I\n"
        "Item 1. | Financial Statements | 1\n"
        "Item 2. | MD&A | 14\n"
        "Part II\n"
        "Item 1. | Legal Proceedings | 20\n"
        "Item 1A. | Risk Factors | 20\n"
        "\n"
        "PART I  —  FINANCIAL INFORMATION\n"
        "Item 1.    Financial Statements\n"
        "Condensed consolidated statements of operations.\n"
        "\n"
        "Item 2.    Management's Discussion and Analysis\n"
        "Revenue was strong in the quarter.\n"
        "\n"
        "PART II  —  OTHER INFORMATION\n"
        "Item 1.    Legal Proceedings\n"
        "There are no pending legal proceedings.\n"
        "\n"
        "Item 1A.    Risk Factors\n"
        "Risk factors remain substantially the same as in the 10-K.\n"
    )


@pytest.fixture
def large_section_text() -> str:
    """A section body exceeding 2000 chars for sub-chunking tests."""
    # Each sentence ~100 chars, 25 sentences = ~2500 chars
    sentences = [
        f"Sentence number {i:03d} provides important information about the company's operations and strategy. "
        for i in range(25)
    ]
    return "".join(sentences)
