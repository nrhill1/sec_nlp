# tests/core/test_loader.py
"""Unit tests for Loader with direct fetch, auto CIK lookup, and keyword filtering."""

from pathlib import Path

import pytest

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.ingest import parser as parser_module
from sec_nlp.core.ingest.loader import Loader, LoaderRunMetadata
from sec_nlp.core.text.filters import create_item_filter
from sec_nlp.core.text.semantic_settings import SemanticChunkingSettings


@pytest.fixture
def loader_with_mock_filings(mock_filing_structure: Path) -> Loader:
    """Loader configured for disk-based testing with mock filings."""
    loader = Loader(
        email="test@example.com",
        company_name="Test Company",
        downloads_folder=mock_filing_structure,
        fetch_mode="download",
        chunk_size=500,
        chunk_overlap=50,
    )
    loader.add_symbols(["AAPL", "MSFT"])
    return loader


class TestLoaderDefaults:
    """Test default configuration values."""

    def test_default_fetch_mode_is_download(self) -> None:
        loader = Loader(email="test@example.com")
        assert loader.fetch_mode == "download"

    def test_default_keyword_mode_is_any(self) -> None:
        loader = Loader(email="test@example.com")
        assert loader.keyword_mode == "any"

    def test_default_keywords_is_none(self) -> None:
        loader = Loader(email="test@example.com")
        assert loader.keywords is None


class TestAddSymbols:
    """Test adding symbols without CIK parameters."""

    def test_add_single_symbol(self) -> None:
        loader = Loader(email="test@example.com")
        loader.add_symbol("AAPL")
        assert "AAPL" in loader._symbols

    def test_add_multiple_symbols(self) -> None:
        loader = Loader(email="test@example.com")
        loader.add_symbols(["AAPL", "MSFT", "GOOGL"])
        assert loader._symbols == {"AAPL", "MSFT", "GOOGL"}

    def test_add_symbol_normalizes_case(self) -> None:
        loader = Loader(email="test@example.com")
        loader.add_symbol("aapl")
        assert "AAPL" in loader._symbols

    def test_add_symbol_strips_whitespace(self) -> None:
        loader = Loader(email="test@example.com")
        loader.add_symbol("  AAPL  ")
        assert "AAPL" in loader._symbols

    def test_add_symbols_no_cik_parameter(self) -> None:
        """Verify add_symbols doesn't require CIK parameter."""
        loader = Loader(email="test@example.com")
        # This should work without any CIK parameter
        loader.add_symbols(["AAPL", "MSFT"])
        assert len(loader._symbols) == 2


class TestLoadDocumentsDiskMode:
    """Test load_documents in disk/download mode."""

    def test_load_documents_uses_existing_files_without_download(
        self, loader_with_mock_filings: Loader
    ) -> None:
        docs = loader_with_mock_filings.load_documents(
            mode=FilingMode.annual,
            limit_per_symbol=1,
            perform_download=False,
        )

        assert isinstance(docs, list)
        assert all(isinstance(d, Document) for d in docs)
        assert len(docs) >= 1

    def test_last_meta_is_populated(
        self, loader_with_mock_filings: Loader
    ) -> None:
        _ = loader_with_mock_filings.load_documents(
            mode=FilingMode.annual,
            limit_per_symbol=1,
            perform_download=False,
        )

        meta: LoaderRunMetadata = loader_with_mock_filings.last_meta
        assert "per_symbol_doc_counts" in meta
        assert meta["total_documents"] >= 1

        # When skipping download, download_results should be empty dict
        assert meta["download_results"] == {}

    def test_load_texts_returns_strings(
        self, loader_with_mock_filings: Loader
    ) -> None:
        texts = loader_with_mock_filings.load_texts(
            mode=FilingMode.annual,
            limit_per_symbol=1,
            perform_download=False,
        )

        assert isinstance(texts, list)
        assert all(isinstance(t, str) for t in texts)
        assert len(texts) >= 1


def test_html_paths_for_symbol_current_mode_includes_8k_and_6k(
    tmp_path: Path,
) -> None:
    symbol = "AAPL"
    for form in ("8-K", "6-K"):
        accession_dir = (
            tmp_path
            / "sec-edgar-filings"
            / symbol
            / form
            / f"0000000000-26-00000{1 if form == '8-K' else 2}"
        )
        accession_dir.mkdir(parents=True, exist_ok=True)
        (accession_dir / "full-submission.txt").write_text(
            "FILED AS OF DATE:\t\t20260201\n",
            encoding="utf-8",
        )
        (accession_dir / f"{form.lower()}_filing.html").write_text(
            f"<html><body>{form} filing</body></html>",
            encoding="utf-8",
        )

    loader = Loader(
        email="test@example.com",
        downloads_folder=tmp_path,
        fetch_mode="download",
    )

    html_paths = loader.html_paths_for_symbol(
        symbol=symbol,
        mode=FilingMode.current,
        base=tmp_path,
    )

    assert len(html_paths) == 2
    assert {path.parent.parent.name for path in html_paths} == {"8-K", "6-K"}


class TestKeywordFiltering:
    """Test keyword filtering functionality."""

    def test_keyword_filtering_with_instance_keywords(
        self, mock_filing_structure: Path
    ) -> None:
        """Test filtering using keywords set at instance level."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=mock_filing_structure,
            fetch_mode="download",
            keywords=["Apple"],  # Only match Apple content
        )
        loader.add_symbols(["AAPL", "MSFT"])

        docs = loader.load_documents(
            mode=FilingMode.annual,
            perform_download=False,
        )

        # Should have documents, but only from AAPL
        assert len(docs) > 0
        # All documents should contain "Apple" (case-insensitive)
        for doc in docs:
            assert "apple" in doc.page_content.lower()

    def test_keyword_filtering_with_parameter_keywords(
        self, mock_filing_structure: Path
    ) -> None:
        """Test filtering using keywords passed to load_documents."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=mock_filing_structure,
            fetch_mode="download",
        )
        loader.add_symbols(["AAPL", "MSFT"])

        docs = loader.load_documents(
            mode=FilingMode.annual,
            perform_download=False,
            keywords=["Microsoft"],
        )

        # Should only get Microsoft content
        assert len(docs) > 0
        for doc in docs:
            assert "microsoft" in doc.page_content.lower()

    def test_keyword_filtering_parameter_overrides_instance(
        self, mock_filing_structure: Path
    ) -> None:
        """Test that parameter keywords override instance keywords."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=mock_filing_structure,
            fetch_mode="download",
            keywords=["Apple"],  # Instance level
        )
        loader.add_symbols(["AAPL", "MSFT"])

        # Override with parameter
        docs = loader.load_documents(
            mode=FilingMode.annual,
            perform_download=False,
            keywords=["Microsoft"],  # Parameter level
        )

        # Should use parameter keywords (Microsoft), not instance keywords (Apple)
        assert len(docs) > 0
        for doc in docs:
            assert "microsoft" in doc.page_content.lower()

    def test_keyword_mode_any(self, mock_filing_structure: Path) -> None:
        """Test keyword_mode='any' matches documents with any keyword."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=mock_filing_structure,
            fetch_mode="download",
            keywords=["Apple", "Microsoft"],
            keyword_mode="any",
        )
        loader.add_symbols(["AAPL", "MSFT"])

        docs = loader.load_documents(
            mode=FilingMode.annual,
            perform_download=False,
        )

        # Should get both Apple and Microsoft documents
        assert len(docs) > 0

    def test_keyword_mode_all(self, mock_filing_structure: Path) -> None:
        """Test keyword_mode='all' requires all keywords."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=mock_filing_structure,
            fetch_mode="download",
            keywords=["Filing", "Content"],  # Both present in mock HTML
            keyword_mode="all",
        )
        loader.add_symbols(["AAPL"])

        docs = loader.load_documents(
            mode=FilingMode.annual,
            perform_download=False,
        )

        # Should get documents since both keywords are present
        assert len(docs) > 0
        for doc in docs:
            content_lower = doc.page_content.lower()
            assert "filing" in content_lower
            assert "content" in content_lower


class TestTransformHtml:
    """Test HTML transformation methods."""

    def test_transform_html_with_keywords(
        self, mock_filing_structure: Path
    ) -> None:
        """Test transform_html with keyword filtering."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=mock_filing_structure,
            fetch_mode="download",
        )

        html_path = (
            mock_filing_structure
            / "sec-edgar-filings"
            / "AAPL"
            / "10-K"
            / "0001234567"
            / "filing.html"
        )

        docs = loader.transform_html(html_path, keywords=["Apple"])

        assert len(docs) > 0
        for doc in docs:
            assert "apple" in doc.page_content.lower()

    def test_transform_html_string_with_keywords(self) -> None:
        """Test transform_html_string with keyword filtering."""
        loader = Loader(email="test@example.com")

        html = """
        <html>
            <body>
                <p>Product warranty information</p>
                <p>Company overview</p>
                <p>Warranty coverage details</p>
            </body>
        </html>
        """

        docs = loader.transform_html_string(html, keywords=["warranty"])

        # Should only get elements containing "warranty"
        assert len(docs) > 0
        for doc in docs:
            assert "warranty" in doc.page_content.lower()

    def test_transform_html_string_preserves_section_headers_for_keyword_filter(
        self,
    ) -> None:
        """Test section extraction before keyword filtering when section filter is active."""
        loader = Loader(
            email="test@example.com",
            semantic_chunking=SemanticChunkingSettings(enabled=False),
        )

        html = """
        <html>
            <body>
                <p>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</p>
                <p>Government contracts expanded during the quarter and supported new bookings.</p>
                <p>Cash runway also improved as operating losses narrowed.</p>
                <p>Item 8. Financial Statements and Supplementary Data</p>
                <p>Balance sheet tables follow.</p>
            </body>
        </html>
        """

        docs = loader.transform_html_string(
            html,
            keywords=["government contracts"],
            section_filter=create_item_filter(["7"]),
        )

        assert len(docs) > 0
        assert all(doc.metadata.get("section_number") == "7" for doc in docs)
        assert any(
            "government contracts" in doc.page_content.lower() for doc in docs
        )

    def test_transform_html_string_returns_empty_on_no_match(self) -> None:
        """Test that transform_html_string returns empty list when no keywords match."""
        loader = Loader(email="test@example.com")

        html = (
            "<html><body><p>Some content without the keyword</p></body></html>"
        )

        docs = loader.transform_html_string(html, keywords=["nonexistent"])

        assert len(docs) == 0

    def test_transform_html_falls_back_when_spacy_download_fails(
        self,
        mock_filing_structure: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test file parsing fallback when unstructured cannot fetch spaCy."""

        def _raise_spacy_download_error(
            **_kwargs,
        ) -> list[Document]:
            raise RuntimeError(
                "Failed to download spaCy model from https://github.com/explosion/..."
            )

        monkeypatch.setattr(
            "sec_nlp.core.ingest.parser._require_local_html_model", lambda: None
        )
        monkeypatch.setattr(
            "unstructured.partition.html.partition_html",
            _raise_spacy_download_error,
        )

        loader = Loader(
            email="test@example.com",
            downloads_folder=mock_filing_structure,
            fetch_mode="download",
        )
        html_path = (
            mock_filing_structure
            / "sec-edgar-filings"
            / "AAPL"
            / "10-K"
            / "0001234567"
            / "filing.html"
        )

        docs = loader.transform_html(html_path, keywords=["Apple"])

        assert len(docs) > 0
        assert all("apple" in doc.page_content.lower() for doc in docs)
        assert all(doc.metadata.get("source") == str(html_path) for doc in docs)

    def test_transform_html_string_falls_back_when_spacy_download_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test string parsing fallback when partition_html cannot fetch spaCy."""

        def _raise_spacy_download_error(*args, **kwargs) -> None:
            _ = args
            _ = kwargs
            raise RuntimeError(
                "Failed to download spaCy model from https://github.com/explosion/..."
            )

        monkeypatch.setattr(
            "sec_nlp.core.ingest.parser._require_local_html_model", lambda: None
        )
        monkeypatch.setattr(
            "unstructured.partition.html.partition_html",
            _raise_spacy_download_error,
        )

        loader = Loader(email="test@example.com")
        html = """
        <html>
            <body>
                <p>Product warranty information</p>
                <p>Company overview</p>
                <p>Warranty coverage details</p>
            </body>
        </html>
        """

        docs = loader.transform_html_string(html, keywords=["warranty"])

        assert len(docs) > 0
        assert all("warranty" in doc.page_content.lower() for doc in docs)

    def test_transform_html_falls_back_when_socket_is_blocked(
        self,
        mock_filing_structure: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test file parsing fallback when parser network access is blocked."""

        def _raise_socket_blocked(
            **_kwargs,
        ) -> list[Document]:
            raise RuntimeError("A test tried to use socket.socket.")

        monkeypatch.setattr(
            "sec_nlp.core.ingest.parser._require_local_html_model", lambda: None
        )
        monkeypatch.setattr(
            "unstructured.partition.html.partition_html",
            _raise_socket_blocked,
        )

        loader = Loader(
            email="test@example.com",
            downloads_folder=mock_filing_structure,
            fetch_mode="download",
        )
        html_path = (
            mock_filing_structure
            / "sec-edgar-filings"
            / "AAPL"
            / "10-K"
            / "0001234567"
            / "filing.html"
        )

        docs = loader.transform_html(html_path, keywords=["Apple"])

        assert len(docs) > 0
        assert all("apple" in doc.page_content.lower() for doc in docs)


class TestLoaderRepr:
    """Test string representations."""

    def test_repr_includes_fetch_mode(self) -> None:
        loader = Loader(email="test@example.com")
        loader.add_symbols(["AAPL"])
        repr_str = repr(loader)
        assert "fetch_mode=download" in repr_str
        assert "AAPL" in repr_str

    def test_str_shows_mode(self) -> None:
        loader = Loader(email="test@example.com", fetch_mode="download")
        loader.add_symbols(["AAPL", "MSFT"])
        str_rep = str(loader)
        assert "download" in str_rep
        assert "2 symbol" in str_rep


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_load_documents_without_symbols_raises_error(self) -> None:
        loader = Loader(email="test@example.com")
        with pytest.raises(ValueError, match="No symbols added"):
            loader.load_documents()
