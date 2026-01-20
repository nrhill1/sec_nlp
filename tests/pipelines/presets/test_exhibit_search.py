# tests/pipelines/presets/test_exhibit_search.py
"""Unit tests for ExhibitSearch semantic search functionality."""

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from langchain_qdrant import QdrantVectorStore

from sec_nlp.pipelines.presets.exb.steps.search.search import (
    ExhibitSearch,
    SearchResult,
)
from sec_nlp.pipelines.presets.exb.steps.search.search_config import (
    SearchConfig,
)


class TestSearchConfig:
    """Tests for SearchConfig model."""

    def test_search_config_default_values(self) -> None:
        """Test that SearchConfig has correct default values."""
        config = SearchConfig()

        assert config.queries == [
            "Supply agreements with exclusivity for diesel engine components",
            "Contracts providing parts at cost or cost-plus pricing to OEMs",
            "Aftermarket repair, replacement, or maintenance obligations for parts",
            "Exclusive supplier agreements covering diesel engine parts and services",
            "Aftermarket service and parts pricing provisions",
        ]
        assert config.limit == 30
        assert config.score_threshold == 0.9
        assert config.export_results is True

    def test_search_config_with_custom_values(self) -> None:
        """Test creating SearchConfig with custom values."""
        config = SearchConfig(
            queries=["exclusive contracts", "aftermarket provisions"],
            limit=20,
            score_threshold=0.7,
            export_results=False,
        )

        assert len(config.queries) == 2
        assert "exclusive contracts" in config.queries
        assert config.limit == 20
        assert config.score_threshold == 0.7
        assert config.export_results is False


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_search_result_creation(self) -> None:
        """Test creating SearchResult with valid data."""
        result = SearchResult(
            text="Test contract text",
            score=0.85,
            metadata={"symbol": "CAT", "contract_type": "Supply Agreement"},
        )

        assert result.text == "Test contract text"
        assert result.score == 0.85
        assert result.metadata["symbol"] == "CAT"

    def test_search_result_default_metadata(self) -> None:
        """Test that metadata defaults to empty dict."""
        result = SearchResult(text="test", score=0.5)
        assert result.metadata == {}


class TestExhibitSearch:
    """Tests for ExhibitSearch functionality."""

    def make_vector_store(self) -> MagicMock:
        """Create a MagicMock that mimics QdrantVectorStore."""
        store = MagicMock(spec=QdrantVectorStore)
        store.collection_name = "exhibit"
        store.client = MagicMock()
        store.client.get_collections.return_value = Mock(collections=[])
        store.client.get_collection = MagicMock(return_value=Mock())
        store.client.collection_exists = MagicMock(return_value=True)
        store.similarity_search_with_score = MagicMock(return_value=[])
        store.max_marginal_relevance_search = MagicMock(return_value=[])
        return store

    @pytest.fixture
    def mock_vector_store(self) -> MagicMock:
        """Create a mock QdrantVectorStore instance with helper defaults."""
        return self.make_vector_store()

    def test_exhibit_search_initialization(
        self,
    ) -> None:
        """Test basic initialization of ExhibitSearch."""
        search = ExhibitSearch(vector_store=self.make_vector_store())

        assert search.limit == 30
        assert search.score_threshold == 0.9

    def test_exhibit_search_with_custom_config(
        self, mock_vector_store: Mock
    ) -> None:
        """Test initialization with custom configuration."""
        search = ExhibitSearch(
            vector_store=mock_vector_store,
            limit=20,
            score_threshold=0.7,
        )

        assert search.limit == 20
        assert search.score_threshold == 0.7

    def test_search_no_collections(self, mock_vector_store: Mock) -> None:
        """Test search returns empty list when no collections found."""
        mock_vector_store.client.get_collection.side_effect = Exception(
            "missing collection"
        )

        search = ExhibitSearch(vector_store=mock_vector_store)
        results = search.search("test query")

        assert results == []

    def test_search_with_symbols_filter(self, mock_vector_store: Mock) -> None:
        """Test search filters by symbols when provided."""
        mock_vector_store.search.return_value = []

        search = ExhibitSearch(vector_store=mock_vector_store)
        results = search.search("test query", symbols=["CAT", "DE"])

        assert results == []

    def test_search_returns_sorted_results(
        self, mock_vector_store: Mock
    ) -> None:
        """Test that search results are sorted by score descending."""
        from langchain_core.documents import Document

        # Create mock Documents with scores (similarity_search_with_score returns tuples)
        doc1 = Document(
            page_content="result 1", metadata={"accession_number": "acc1"}
        )
        doc2 = Document(
            page_content="result 2", metadata={"accession_number": "acc2"}
        )
        doc3 = Document(
            page_content="result 3", metadata={"accession_number": "acc3"}
        )

        mock_vector_store.similarity_search_with_score.return_value = [
            (doc1, 0.95),
            (doc2, 0.85),  # Below default threshold, should be filtered out
            (doc3, 0.92),
        ]

        search = ExhibitSearch(vector_store=mock_vector_store)
        results = search.search("test query")

        assert len(results) == 2
        assert [r.score for r in results] == [0.95, 0.92]

    def test_search_respects_limit(self, mock_vector_store: Mock) -> None:
        """Test that search respects the limit parameter."""
        from langchain_core.documents import Document

        # Create 10 mock results as (Document, score) tuples
        mock_results = []
        for i in range(10):
            doc = Document(
                page_content=f"result {i}",
                metadata={"accession_number": f"acc{i}"},
            )
            mock_results.append((doc, 0.8 + (i * 0.01)))

        mock_vector_store.similarity_search_with_score.return_value = (
            mock_results
        )

        search = ExhibitSearch(vector_store=mock_vector_store, limit=5)
        results = search.search("test query")

        # Results are limited and deduped by accession
        assert len(results) <= 5

    def test_export_results_creates_yaml_file(
        self, mock_vector_store: Mock, tmp_path: Path
    ) -> None:
        """Test that export_results creates a YAML file."""
        import yaml

        search = ExhibitSearch(vector_store=mock_vector_store)

        results = [
            SearchResult(
                text="test contract text",
                score=0.8,
                metadata={
                    "symbol": "CAT",
                    "accession_number": "0001234-24-000001",
                    "doc_type": "EX-10.1",
                    "filing_date": "2024-01-15",
                },
            )
        ]

        output_file = tmp_path / "test_results.yaml"
        search.export_results(
            query="test query",
            results=results,
            output_path=output_file,
        )

        assert output_file.exists()
        data = yaml.safe_load(output_file.read_text())
        assert data["query"] == "test query"
        assert data["count"] == 1
        hit = data["hits"][0]
        assert hit["accession"] == "0001234-24-000001"
        assert hit["symbol"] == "CAT"
        assert hit["doc_type"] == "EX-10.1"
        assert hit["filed"] == "2024-01-15"
        assert hit["score"] == 0.8
        assert "excerpt" not in hit  # No text in output

    def test_export_results_converts_json_to_yaml(
        self, mock_vector_store: Mock, tmp_path: Path
    ) -> None:
        """Test export_results converts .json extension to .yaml."""
        search = ExhibitSearch(vector_store=mock_vector_store)

        results = [SearchResult(text="test", score=0.8, metadata={})]

        output_file = tmp_path / "test_results.json"
        search.export_results(
            query="test query",
            results=results,
            output_path=output_file,
        )

        # Should create .yaml file, not .json
        yaml_file = tmp_path / "test_results.yaml"
        assert yaml_file.exists()
        assert not output_file.exists()


class TestExhibitSearchIntegration:
    """Integration tests for search functionality in pipeline."""

    def test_search_config_integration_in_pipeline_config(
        self, tmp_path: Path
    ) -> None:
        """Test that SearchConfig integrates properly with ExhibitConfig."""
        from sec_nlp.pipelines.presets.exb import ExhibitConfig

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        config = ExhibitConfig(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        # Should have search config with defaults
        assert config.search.queries == [
            "Supply agreements with exclusivity for diesel engine components",
            "Contracts providing parts at cost or cost-plus pricing to OEMs",
            "Aftermarket repair, replacement, or maintenance obligations for parts",
            "Exclusive supplier agreements covering diesel engine parts and services",
            "Aftermarket service and parts pricing provisions",
        ]

    def test_search_config_with_custom_queries(self, tmp_path: Path) -> None:
        """Test configuring search with custom queries."""
        from sec_nlp.pipelines.presets.exb import (
            ExhibitConfig,
            SearchConfig,
        )

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir()
        out_path.mkdir()

        config = ExhibitConfig(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            search=SearchConfig(
                queries=[
                    "exclusive supply agreements",
                    "aftermarket provisions",
                ],
                limit=15,
            ),
        )

        assert len(config.search.queries) == 2
        assert config.search.limit == 15
