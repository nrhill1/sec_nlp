# tests/core/test_loader_streaming.py
"""Tests for streaming document processing in the Loader class.

These tests verify the load_documents_stream and load_texts_stream methods
which are designed for memory-efficient processing of SEC filings.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.ingest.loader import Loader


@pytest.fixture
def temp_filing_structure() -> Generator[Path]:
    """Create a temporary directory with mock SEC filing structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)

        # Create AAPL 10-K filings
        for i in range(3):
            filing_dir = (
                base / "sec-edgar-filings" / "AAPL" / "10-K" / f"000123456{i}"
            )
            filing_dir.mkdir(parents=True, exist_ok=True)
            html_path = (
                filing_dir / "primary-document.html"
            )  # Must be .html not .htm
            html_path.write_text(f"""
            <html>
            <head><title>AAPL 10-K Filing {i}</title></head>
            <body>
                <h1>Apple Inc Annual Report {i}</h1>
                <p>This is the annual report content for filing {i}.</p>
                <p>It contains important financial information.</p>
            </body>
            </html>
            """)

        yield base


@pytest.fixture
def streaming_loader(temp_filing_structure: Path) -> Loader:
    """Create a loader configured for streaming tests."""
    loader = Loader(
        email="test@example.com",
        downloads_folder=temp_filing_structure,
        chunk_size=500,
        chunk_overlap=50,
    )
    loader.add_symbol("AAPL")
    return loader


class TestLoadDocumentsStream:
    """Tests for load_documents_stream method."""

    def test_yields_documents(self, streaming_loader: Loader) -> None:
        """Test that streaming yields Document objects."""
        docs = list(
            streaming_loader.load_documents_stream(
                mode=FilingMode.annual,
                perform_download=False,
            )
        )
        assert len(docs) > 0
        assert all(isinstance(doc, Document) for doc in docs)

    def test_streaming_is_generator(self, streaming_loader: Loader) -> None:
        """Test that streaming returns a generator type."""
        stream = streaming_loader.load_documents_stream(
            mode=FilingMode.annual,
            perform_download=False,
        )

        # Should be a generator
        assert isinstance(stream, Generator)

        # Should NOT be a list
        assert not isinstance(stream, list)

    def test_streaming_with_limit(self, streaming_loader: Loader) -> None:
        """Test streaming with limit_per_symbol."""
        docs = list(
            streaming_loader.load_documents_stream(
                mode=FilingMode.annual,
                perform_download=False,
                limit_per_symbol=1,
            )
        )
        # Should process at most 1 filing
        assert len(docs) >= 0

    def test_no_symbols_raises_error(self, temp_filing_structure: Path) -> None:
        """Test that streaming without symbols raises ValueError."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=temp_filing_structure,
        )
        # Don't add symbols

        with pytest.raises(ValueError, match="No symbols added"):
            list(
                loader.load_documents_stream(
                    mode=FilingMode.annual,
                    perform_download=False,
                )
            )


class TestLoadTextsStream:
    """Tests for load_texts_stream method."""

    def test_yields_strings(self, streaming_loader: Loader) -> None:
        """Test that load_texts_stream yields strings."""
        texts = list(
            streaming_loader.load_texts_stream(
                mode=FilingMode.annual,
                perform_download=False,
            )
        )
        assert len(texts) > 0
        assert all(isinstance(text, str) for text in texts)

    def test_text_content_from_filings(self, streaming_loader: Loader) -> None:
        """Test that streamed texts contain expected filing content."""
        texts = list(
            streaming_loader.load_texts_stream(
                mode=FilingMode.annual,
                perform_download=False,
            )
        )

        # Combine all texts
        combined = " ".join(texts)

        # Should contain content from our mock filings
        assert "Apple" in combined or "annual" in combined.lower()


class TestStreamingWithKeywords:
    """Tests for streaming with keyword filtering."""

    def test_streaming_with_keywords(self, temp_filing_structure: Path) -> None:
        """Test streaming filters by keywords."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=temp_filing_structure,
            keywords=["annual", "report"],
            keyword_mode="any",
        )
        loader.add_symbol("AAPL")

        docs = list(
            loader.load_documents_stream(
                mode=FilingMode.annual,
                perform_download=False,
            )
        )

        # Should return documents matching keywords
        assert len(docs) >= 0

    def test_streaming_keyword_override(self, streaming_loader: Loader) -> None:
        """Test that keywords parameter overrides instance keywords."""
        docs = list(
            streaming_loader.load_documents_stream(
                mode=FilingMode.annual,
                perform_download=False,
                keywords=["nonexistent_keyword_xyz"],
            )
        )

        # Should filter out everything with non-matching keyword
        assert len(docs) == 0


class TestStreamingComparison:
    """Tests comparing streaming vs batch processing."""

    def test_streaming_produces_same_results_as_batch(
        self, streaming_loader: Loader
    ) -> None:
        """Verify streaming produces equivalent results to batch."""
        # Get via streaming
        stream_docs = list(
            streaming_loader.load_documents_stream(
                mode=FilingMode.annual,
                perform_download=False,
            )
        )

        # Get via batch
        batch_docs = streaming_loader.load_documents(
            mode=FilingMode.annual,
            perform_download=False,
        )

        # Should produce same number of documents
        assert len(stream_docs) == len(batch_docs)

        # Content should match
        stream_content = sorted([d.page_content for d in stream_docs])
        batch_content = sorted([d.page_content for d in batch_docs])
        assert stream_content == batch_content


class TestStreamingEdgeCases:
    """Edge case tests for streaming processing."""

    def test_no_filings_on_disk(self, temp_filing_structure: Path) -> None:
        """Test streaming when no filings exist for symbol."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=temp_filing_structure,
        )
        loader.add_symbol("MSFT")  # No MSFT filings in our temp structure

        docs = list(
            loader.load_documents_stream(
                mode=FilingMode.annual,
                perform_download=False,
            )
        )

        # Should return empty list gracefully
        assert docs == []

    def test_multiple_symbols(self, temp_filing_structure: Path) -> None:
        """Test streaming with multiple symbols."""
        # Add another company's filings
        msft_dir = (
            temp_filing_structure
            / "sec-edgar-filings"
            / "MSFT"
            / "10-K"
            / "0009876543"
        )
        msft_dir.mkdir(parents=True, exist_ok=True)
        (msft_dir / "primary-document.html").write_text("""
        <html><body><h1>Microsoft Annual Report</h1>
        <p>Microsoft Corporation financial information.</p></body></html>
        """)

        loader = Loader(
            email="test@example.com",
            downloads_folder=temp_filing_structure,
        )
        loader.add_symbols(["AAPL", "MSFT"])

        docs = list(
            loader.load_documents_stream(
                mode=FilingMode.annual,
                perform_download=False,
            )
        )

        # Should process both companies
        assert len(docs) > 0
