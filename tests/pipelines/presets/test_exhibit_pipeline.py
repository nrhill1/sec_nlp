# tests/pipelines/presets/test_exhibit_pipeline.py
"""Unit tests for sec_nlp.pipelines.presets.exb.pipeline module."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from sec_nlp.pipelines.presets.exb.config import ExhibitConfig
from sec_nlp.pipelines.presets.exb.models import (
    ExhibitContractResult,
    ExhibitResult,
)
from sec_nlp.pipelines.presets.exb.pipeline import ExhibitPipeline
from sec_nlp.pipelines.presets.exb.run_stages import (
    build_exhibit_stage_chain,
    create_initial_exhibit_state,
)
from sec_nlp.pipelines.vector import VectorConfig


class TestExhibitPipeline:
    """Tests for ExhibitPipeline initialization and configuration."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> ExhibitConfig:
        """Create a mock ExhibitConfig for testing."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir(parents=True, exist_ok=True)
        out_path.mkdir(parents=True, exist_ok=True)

        return ExhibitConfig(
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
            "sec_nlp.pipelines.presets.exb.pipeline.Loader"
        ) as mock_loader:
            mock_loader.return_value = MagicMock()
            yield

    def test_pipeline_initializes_in_dry_run(
        self, mock_config: ExhibitConfig, mock_dependencies: None
    ) -> None:
        """Test that ExhibitPipeline initializes correctly in dry_run mode."""
        pipeline = ExhibitPipeline(config=mock_config)

        # Verify pipeline attributes
        assert pipeline.pipeline_type == "exhibit"
        assert (
            pipeline.requires_llm is False
        )  # exb pipeline doesn't require LLM
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

        config_annual = ExhibitConfig(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            mode=FilingMode.annual,
        )
        assert config_annual.mode == FilingMode.annual

        config_quarterly = ExhibitConfig(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            mode=FilingMode.quarterly,
        )
        assert config_quarterly.mode == FilingMode.quarterly

    def test_pipeline_config_has_search_terms(
        self, mock_config: ExhibitConfig
    ) -> None:
        """Test that config includes search terms for filtering."""
        assert isinstance(mock_config.search_terms, list)
        assert len(mock_config.search_terms) > 0
        assert "exclusive" in mock_config.search_terms
        assert "aftermarket" in mock_config.search_terms

    def test_vector_store_is_none_in_dry_run(
        self, mock_config: ExhibitConfig, mock_dependencies: None
    ) -> None:
        """Test that vector store is not initialized in dry_run mode."""
        pipeline = ExhibitPipeline(config=mock_config)

        assert pipeline._vector_store is None

    def test_pipeline_has_required_class_attributes(
        self, mock_config: ExhibitConfig, mock_dependencies: None
    ) -> None:
        """Test that pipeline has all required class attributes."""
        pipeline = ExhibitPipeline(config=mock_config)

        assert pipeline.pipeline_type == "exhibit"
        assert pipeline.requires_llm is False
        assert pipeline.requires_vector_db is True
        assert pipeline.get_config_model() == ExhibitConfig
        assert pipeline.get_result_model() == ExhibitResult
        assert "exhibit" in pipeline.description.lower()

    def test_filter_chunks_drops_short_and_duplicates(
        self, mock_config: ExhibitConfig, mock_dependencies: None
    ) -> None:
        """Ensure chunk filtering removes short/duplicate content and keeps keyword hits."""
        pipeline = ExhibitPipeline(config=mock_config)

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

    def test_process_symbol_passes_candidate_accessions(
        self, mock_config: ExhibitConfig, mock_dependencies: None
    ) -> None:
        """Candidate-first mode should pass narrowed accession list to extract step."""
        config = mock_config.model_copy(
            update={
                "candidate_first": True,
                "candidate_fallback_full_scan": False,
            }
        )
        pipeline = ExhibitPipeline(config=config)

        with (
            patch(
                "sec_nlp.pipelines.presets.exb.pipeline.build_candidate_accessions",
                return_value={"0001234567-26-000001"},
            ) as candidate_mock,
            patch(
                "sec_nlp.pipelines.presets.exb.pipeline.collect_exhibit_documents",
                return_value=([], MagicMock()),
            ) as collect_mock,
        ):
            outputs = pipeline._process_symbol("CAT")

        assert outputs == []
        assert candidate_mock.called
        assert collect_mock.call_args.kwargs["allowed_accessions"] == {
            "0001234567-26-000001"
        }

    def test_exhibit_stage_chain_preserves_state_identity(
        self,
        mock_config: ExhibitConfig,
        mock_dependencies: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Stage chain should mutate one state object in place."""
        pipeline = ExhibitPipeline(config=mock_config)
        monkeypatch.setattr(
            "sec_nlp.pipelines.presets.exb.pipeline.build_candidate_accessions",
            lambda symbol, config: set(),
        )
        monkeypatch.setattr(
            "sec_nlp.pipelines.presets.exb.pipeline.collect_exhibit_documents",
            lambda loader,
            symbol,
            config,
            keyword_terms,
            keyword_categories,
            adaptive_chunk_size,
            skip_prefilter,
            allowed_accessions: (
                [
                    Document(
                        page_content=("exclusive supply agreement " * 30),
                        metadata={"accession_number": "0001"},
                    )
                ],
                MagicMock(),
            ),
        )
        monkeypatch.setattr(
            "sec_nlp.pipelines.presets.exb.run_stages.write_exhibit_outputs",
            lambda symbol, docs, config: [],
        )
        monkeypatch.setattr(
            "sec_nlp.pipelines.presets.exb.run_stages.write_exhibit_summary",
            lambda symbol, docs, config: [],
        )

        stage_chain = build_exhibit_stage_chain(pipeline)
        state = create_initial_exhibit_state(
            runtime=pipeline,
            symbol="CAT",
            include_bridge=True,
        )
        final_state = pipeline.run_stage_chain(
            initial_state=state,
            stage_chain=stage_chain,
        )
        assert id(final_state) == id(state)


class TestExhibitContractResult:
    """Tests for ExhibitContractResult model."""

    def test_analysis_result_default_values(self) -> None:
        """Test that contract result has correct default values."""
        result = ExhibitContractResult()

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
        result = ExhibitContractResult(
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


class TestExhibitConfig:
    """Tests for ExhibitConfig model."""

    def test_config_default_values(self, tmp_path: Path) -> None:
        """Test that config has sensible default values."""
        dl_path = tmp_path / "downloads"
        out_path = tmp_path / "outputs"
        dl_path.mkdir(parents=True, exist_ok=True)
        out_path.mkdir(parents=True, exist_ok=True)

        config = ExhibitConfig(
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

        config = ExhibitConfig(
            email="test@example.com",
            dl_path=dl_path,
            out_path=out_path,
            symbols=["cat", "de", "test"],
        )

        assert config.symbols == ["CAT", "DE", "TEST"]
