# tests/pipelines/presets/test_exhibit10_pipeline.py
"""Unit tests for sec_nlp.pipelines.presets.exb_10.pipeline module."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from sec_nlp.pipelines.presets.exb_10.config import Exhibit10Config
from sec_nlp.pipelines.presets.exb_10.models import (
    Exhibit10ContractResult,
    Exhibit10Result,
)
from sec_nlp.pipelines.presets.exb_10.pipeline import Exhibit10Pipeline
from sec_nlp.pipelines.vector import VectorConfig


class TestExhibit10Pipeline:
    """Tests for Exhibit10Pipeline initialization and configuration."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> Exhibit10Config:
        """Create a mock Exhibit10Config for testing."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir(parents=True, exist_ok=True)
        out_path.mkdir(parents=True, exist_ok=True)

        return Exhibit10Config(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            symbols=["CAT", "DE"],
            dry_run=True,
            vdb=VectorConfig(embedding_model="granite-embedding:30m"),
        )

    @pytest.fixture
    def mock_dependencies(self) -> Generator[None]:
        """Mock all external dependencies required for pipeline initialization."""
        with patch(
            "sec_nlp.pipelines.presets.exb_10.pipeline.Loader"
        ) as mock_loader:
            mock_loader.return_value = MagicMock()
            yield

    def test_pipeline_initializes_in_dry_run(
        self, mock_config: Exhibit10Config, mock_dependencies: None
    ) -> None:
        """Test that Exhibit10Pipeline initializes correctly in dry_run mode."""
        pipeline = Exhibit10Pipeline(config=mock_config)

        # Verify pipeline attributes
        assert pipeline.pipeline_type == "exhibit10"
        assert (
            pipeline.requires_llm is False
        )  # exb_10 pipeline doesn't require LLM
        assert pipeline.requires_vector_db is True

        # Verify vector store is None in dry_run mode
        assert pipeline._vector_store is None

    def test_pipeline_accepts_annual_and_quarterly_modes(
        self, tmp_path: Path
    ) -> None:
        """Test that pipeline accepts annual and quarterly filing modes."""
        from sec_nlp.core.edgar.filing_mode import FilingMode

        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir(parents=True, exist_ok=True)
        out_path.mkdir(parents=True, exist_ok=True)

        config_annual = Exhibit10Config(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            mode=FilingMode.annual,
        )
        assert config_annual.mode == FilingMode.annual

        config_quarterly = Exhibit10Config(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            mode=FilingMode.quarterly,
        )
        assert config_quarterly.mode == FilingMode.quarterly

    def test_pipeline_config_has_search_terms(
        self, mock_config: Exhibit10Config
    ) -> None:
        """Test that config includes search terms for filtering."""
        assert isinstance(mock_config.search_terms, list)
        assert len(mock_config.search_terms) > 0
        assert "exclusive" in mock_config.search_terms
        assert "aftermarket" in mock_config.search_terms

    def test_vector_store_is_none_in_dry_run(
        self, mock_config: Exhibit10Config, mock_dependencies: None
    ) -> None:
        """Test that vector store is not initialized in dry_run mode."""
        pipeline = Exhibit10Pipeline(config=mock_config)

        assert pipeline._vector_store is None

    def test_pipeline_has_required_class_attributes(
        self, mock_config: Exhibit10Config, mock_dependencies: None
    ) -> None:
        """Test that pipeline has all required class attributes."""
        pipeline = Exhibit10Pipeline(config=mock_config)

        assert pipeline.pipeline_type == "exhibit10"
        assert pipeline.requires_llm is False
        assert pipeline.requires_vector_db is True
        assert pipeline.get_config_model() == Exhibit10Config
        assert pipeline.get_result_model() == Exhibit10Result
        assert "Exhibit 10" in pipeline.description

    def test_filter_chunks_drops_short_and_duplicates(
        self, mock_config: Exhibit10Config, mock_dependencies: None
    ) -> None:
        """Ensure chunk filtering removes short/duplicate content and keeps keyword hits."""
        pipeline = Exhibit10Pipeline(config=mock_config)

        keyword_text = (
            "exclusive supply agreement " * 30
        )  # contains search term
        non_keyword = "boilerplate terms and conditions " * 30

        docs = [
            Document(page_content=keyword_text, metadata={"id": "keyword"}),
            Document(page_content=non_keyword, metadata={"id": "nonkw"}),
            Document(page_content=non_keyword, metadata={"id": "dupe"}),
            Document(page_content="short snippet", metadata={"id": "short"}),
        ]

        filtered = pipeline._filter_chunks("TEST", docs)

        assert len(filtered) == 2  # short + duplicate removed
        assert filtered[0].metadata.get("id") == "keyword"
        assert all(
            len(doc.page_content) >= mock_config.min_chunk_chars
            for doc in filtered
        )


class TestExhibit10ContractResult:
    """Tests for Exhibit10ContractResult model."""

    def test_analysis_result_default_values(self) -> None:
        """Test that contract result has correct default values."""
        result = Exhibit10ContractResult()

        assert result.is_relevant is False
        assert result.relevance_score is None
        assert result.contract_type is None
        assert result.supplier_names == []
        assert result.key_terms == []
        assert result.has_exclusivity is False
        assert result.has_aftermarket_provisions is False
        assert result.has_pricing_at_cost is False
        assert result.reasoning is None

    def test_analysis_result_with_values(self) -> None:
        """Test creating contract result with specific values."""
        result = Exhibit10ContractResult(
            is_relevant=True,
            relevance_score=0.85,
            contract_type="Supply Agreement",
            supplier_names=["Acme Corp", "Test Inc"],
            key_terms=["exclusive", "aftermarket"],
            has_exclusivity=True,
            has_aftermarket_provisions=True,
            has_pricing_at_cost=False,
            reasoning="Clear supplier contract with exclusivity terms",
        )

        assert result.is_relevant is True
        assert result.relevance_score == 0.85
        assert result.contract_type == "Supply Agreement"
        assert len(result.supplier_names) == 2
        assert "Acme Corp" in result.supplier_names
        assert len(result.key_terms) == 2
        assert result.has_exclusivity is True
        assert result.has_aftermarket_provisions is True
        assert result.has_pricing_at_cost is False


class TestExhibit10Config:
    """Tests for Exhibit10Config model."""

    def test_config_default_values(self, tmp_path: Path) -> None:
        """Test that config has sensible default values."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir(parents=True, exist_ok=True)
        out_path.mkdir(parents=True, exist_ok=True)

        config = Exhibit10Config(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
        )

        assert config.limit == 5
        assert config.batch_size == 16
        assert config.symbols == ["CAT", "DE", "HON", "PCAR", "CMI", "DHR"]
        assert len(config.search_terms) > 0

    def test_config_symbols_normalization(self, tmp_path: Path) -> None:
        """Test that symbols are normalized to uppercase."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir(parents=True, exist_ok=True)
        out_path.mkdir(parents=True, exist_ok=True)

        config = Exhibit10Config(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            symbols=["cat", "de", "test"],
        )

        assert config.symbols == ["CAT", "DE", "TEST"]
