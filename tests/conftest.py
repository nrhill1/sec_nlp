# tests/conftest.py
"""Shared pytest fixtures for sec_nlp tests."""

import asyncio
import logging
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from _pytest.config import Config
from _pytest.logging import LogCaptureFixture

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.types import JsonDict
from tests.fixtures.sample_filings import (
    SAMPLE_ERROR_HTML,
    SAMPLE_EXHIBIT_HTML,
    SAMPLE_ITEM_HTML,
    create_mixed_filings,
    create_sample_filings,
)
from tests.utils.performance import compare_benchmark, memory_tracker
from tests.utils.typing import BenchmarkCompare, MemoryTracker

logger = logging.getLogger(__name__)


class TempPipelineConfig(BasePipelineSettings):
    """Minimal config used to isolate pipeline paths during tests."""

    pipeline_type = "temp_test"

    def pipeline_label(self) -> str:
        return "Temp Test"


def pytest_configure(config: Config) -> None:
    """Pytest hook that runs at the start of the test session."""
    logger.info("=" * 80)


@pytest.fixture
def temp_pipeline_config(tmp_path: Path) -> TempPipelineConfig:
    """Provide a config instance rooted in tmp_path outputs/downloads."""
    outputs_dir = tmp_path / "outputs"
    downloads_dir = tmp_path / "downloads"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    return TempPipelineConfig(out_path=outputs_dir, dl_path=downloads_dir)


@pytest.fixture
def async_test_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Dedicated event loop for async tests to avoid sharing global loop."""
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def temp_downloads_folder() -> Generator[Path]:
    """
    Create a temporary downloads folder for testing.

    This fixture creates a temporary directory that persists for the
    duration of the test and is automatically cleaned up afterwards.

    Yields:
        Path: Path to temporary downloads directory
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_filing_structure(temp_downloads_folder: Path) -> Path:
    """
    Create a complete mock SEC filing directory structure.

    Creates the following structure:
    - sec-edgar-filings/
      - AAPL/
        - 10-K/
          - 0001234567/
            - filing.html
        - 10-Q/
          - 0001234568/
            - filing.html
      - MSFT/
        - 10-K/
          - 0002345678/
            - filing.html

    Args:
        temp_downloads_folder: Temporary directory path

    Returns:
        Path: Base directory containing mock structure
    """
    base = temp_downloads_folder

    # Create AAPL filings
    aapl_10k = base / "sec-edgar-filings" / "AAPL" / "10-K" / "0001234567"
    aapl_10k.mkdir(parents=True, exist_ok=True)
    (aapl_10k / "filing.html").write_text(
        "<html><head><title>AAPL 10-K</title></head>"
        "<body><p>Apple Inc. 10-K Filing Content</p></body></html>"
    )

    aapl_10q = base / "sec-edgar-filings" / "AAPL" / "10-Q" / "0001234568"
    aapl_10q.mkdir(parents=True, exist_ok=True)
    (aapl_10q / "filing.html").write_text(
        "<html><head><title>AAPL 10-Q</title></head>"
        "<body><p>Apple Inc. 10-Q Filing Content</p></body></html>"
    )

    # Create MSFT filings
    msft_10k = base / "sec-edgar-filings" / "MSFT" / "10-K" / "0002345678"
    msft_10k.mkdir(parents=True, exist_ok=True)
    (msft_10k / "filing.html").write_text(
        "<html><head><title>MSFT 10-K</title></head>"
        "<body><p>Microsoft Corporation 10-K Filing Content</p></body></html>"
    )

    return base


@pytest.fixture
def sample_filings_dir(temp_downloads_folder: Path) -> Path:
    """Create a set of sample filings using reusable HTML snippets."""
    create_sample_filings(
        base=temp_downloads_folder,
        ticker="AAPL",
        form="10-K",
        count=3,
        template=SAMPLE_ITEM_HTML,
    )
    create_mixed_filings(
        base=temp_downloads_folder,
        specs=[
            ("MSFT", "10-K", "0002345678"),
            ("GOOGL", "10-K", "0003456789"),
        ],
        template=SAMPLE_EXHIBIT_HTML,
    )
    # Add a short/error page for negative-path tests
    create_mixed_filings(
        base=temp_downloads_folder,
        specs=[("ERROR", "10-K", "0000000000")],
        template=SAMPLE_ERROR_HTML,
    )
    return temp_downloads_folder


@pytest.fixture
def downloader(temp_downloads_folder: Path) -> Loader:
    """
    Create a Downloader instance with temporary downloads folder.

    This fixture provides a properly configured Downloader for testing
    that uses a temporary directory for downloads.

    Args:
        temp_downloads_folder: Temporary directory path

    Returns:
        Downloader: Configured downloader instance
    """
    return Loader(
        email="test@example.com",
        downloads_folder=temp_downloads_folder,
        company_name="Test Company",
    )


@pytest.fixture
def downloader_with_symbols(downloader: Loader) -> Loader:
    """
    Create a Downloader with common test symbols pre-added.

    Args:
        downloader: Base downloader instance

    Returns:
        Downloader: Downloader with AAPL, MSFT, GOOGL symbols
    """
    downloader.add_symbols(["AAPL", "MSFT", "GOOGL"])
    return downloader


@pytest.fixture
def mock_langchain_documents() -> list[Document]:
    """
    Create mock LangChain Document objects for testing.

    Returns:
        list[Document]: List of mock documents with various content
    """
    return [
        Document(
            page_content="This is the first chunk of SEC filing content.",
            metadata={"source": "filing_1.html", "chunk": 0},
        ),
        Document(
            page_content="This is the second chunk with financial data.",
            metadata={"source": "filing_1.html", "chunk": 1},
        ),
        Document(
            page_content="This is the third chunk with risk factors.",
            metadata={"source": "filing_1.html", "chunk": 2},
        ),
    ]


@pytest.fixture
def mock_llm() -> MagicMock:
    """
    Create a mock LLM for testing chains without actual model calls.

    Uses MagicMock to simulate LangChain LLM behavior. While not type-safe
    with create_autospec (to avoid circular imports), this provides sufficient
    isolation for chain testing.

    Returns:
        MagicMock: Mock LLM that returns predictable responses

    Example:
        >>> mock_llm.invoke.return_value = (
        ...     '{"result": "ok"}'
        ... )
        >>> chain = SomeChain(llm=mock_llm)
        >>> result = chain.run()
    """
    mock = MagicMock()
    mock.invoke.return_value = '{"success": true, "summary": "Test summary"}'
    mock.__or__ = MagicMock(return_value=mock)
    mock.invoke_with_metadata = MagicMock(
        return_value='{"success": true, "metadata": {}}'
    )
    return mock


@pytest.fixture
def track_memory() -> MemoryTracker:
    """Return a context manager for tracking memory deltas."""
    return memory_tracker


@pytest.fixture
def benchmark_compare() -> BenchmarkCompare:
    """Compare a runtime against a baseline with tolerance."""

    def _compare(
        current: float, baseline: float, tolerance: float = 0.10
    ) -> bool:
        return compare_benchmark(
            current=current, baseline=baseline, tolerance=tolerance
        )

    return _compare


@pytest.fixture
def mock_html_loader() -> MagicMock:
    """
    Create a mock BSHTMLLoader for testing without actual file I/O.

    This fixture provides a realistic mock that returns LangChain Document
    objects, allowing tests to verify document processing without touching
    the file system.

    Returns:
        MagicMock: Mock loader that returns test documents

    Example:
        >>> documents = (
        ...     mock_html_loader.load_and_split()
        ... )
        >>> assert len(documents) == 1
        >>> assert (
        ...     "Test filing"
        ...     in documents[0].page_content
        ... )
    """
    mock = MagicMock()
    test_doc = Document(
        page_content="Test filing content with multiple sections for processing",
        metadata={
            "source": "test.html",
            "title": "Test Document",
            "date": "2024-01-01",
        },
    )
    mock.load_and_split.return_value = [test_doc]
    mock.load.return_value = [test_doc]
    return mock


# ============================================================================
# MOCK FACTORY FUNCTIONS
# ============================================================================
# These functions help create properly typed mocks using create_autospec or
# MagicMock with spec. Use these patterns when creating test mocks.


def create_mock_documents(
    count: int = 3, content_prefix: str = "Document"
) -> list[Document]:
    """
    Factory function to create mock LangChain Document objects.

    Useful for testing document processing pipelines without creating
    real documents.

    Args:
        count: Number of documents to create
        content_prefix: Prefix for document content

    Returns:
        List of Document objects with distinct content

    Example:
        >>> docs = create_mock_documents(count=5)
        >>> assert len(docs) == 5
        >>> assert all(
        ...     isinstance(d, Document)
        ...     for d in docs
        ... )
    """
    return [
        Document(
            page_content=f"{content_prefix} {i}: Content for chunk {i}",
            metadata={
                "source": f"file_{i}.html",
                "chunk_index": i,
                "accession_number": f"0000000000-00-{i:06d}",
            },
        )
        for i in range(count)
    ]


def create_mock_config_dict(
    **overrides: dict[str, str | bool | list[str]],
) -> dict[str, str | bool | list[str]]:
    """
    Factory function to create mock configuration dictionaries.

    Creates a base config dict and allows overriding specific values.

    Args:
        **overrides: Keys and values to override in the config

    Returns:
        Configuration dictionary for testing

    Example:
        >>> config = create_mock_config_dict(
        ...     verbose=True
        ... )
        >>> assert config["verbose"] is True
    """
    base_config: dict[str, str | bool | list[str]] = {
        "email": "test@example.com",
        "verbose": False,
        "dry_run": False,
        "symbols": ["AAPL"],
    }
    for override in overrides.values():
        base_config.update(override)
    return base_config


# ============================================================================
# END MOCK FACTORY FUNCTIONS
# ============================================================================


@pytest.fixture
def sample_html_content() -> str:
    """
    Provide sample HTML content for testing parsers.

    Returns:
        str: Valid HTML content simulating SEC filing
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>10-K Annual Report</title>
    </head>
    <body>
        <h1>Company Name Inc.</h1>
        <h2>Form 10-K</h2>
        <section id="item1">
            <h3>Item 1. Business</h3>
            <p>This is the business description section with important
            information about the company's operations and strategy.</p>
        </section>
        <section id="item1a">
            <h3>Item 1A. Risk Factors</h3>
            <p>Investment in our securities involves risk. Key risks include
            market volatility, regulatory changes, and competition.</p>
        </section>
        <section id="item7">
            <h3>Item 7. Management's Discussion and Analysis</h3>
            <p>Our financial performance this year was strong with revenue
            increasing by 15% year-over-year to $100 million.</p>
        </section>
    </body>
    </html>
    """


@pytest.fixture
def sample_json_response() -> JsonDict:
    """
    Provide sample JSON response from SEC API.

    Returns:
        dict: Mock SEC API response
    """
    return {
        "cik": "0000320193",
        "entityType": "operating",
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "exchanges": ["Nasdaq"],
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-23-000106"],
                "filingDate": ["2023-11-03"],
                "reportDate": ["2023-09-30"],
                "acceptanceDateTime": ["2023-11-03T18:30:00.000Z"],
                "act": ["34"],
                "form": ["10-K"],
                "fileNumber": ["001-36743"],
                "filmNumber": ["231234567"],
                "items": [""],
                "size": [1234567],
                "isXBRL": [1],
                "isInlineXBRL": [1],
                "primaryDocument": ["aapl-20230930.htm"],
                "primaryDocDescription": ["10-K"],
            }
        },
    }


@pytest.fixture(autouse=True)
def reset_environment() -> Generator[None]:
    """
    Automatically reset environment variables before each test.

    This ensures tests don't interfere with each other through
    environment variable side effects.
    """
    import os

    # Store original environment
    original_env = os.environ.copy()

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def capture_logs(caplog: LogCaptureFixture) -> LogCaptureFixture:
    """
    Fixture to easily capture and inspect log messages.

    Args:
        caplog: pytest's log capture fixture

    Returns:
        caplog: The log capture fixture
    """
    import logging

    caplog.set_level(logging.DEBUG)
    return caplog
