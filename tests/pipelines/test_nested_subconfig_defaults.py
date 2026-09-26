# tests/pipelines/test_nested_subconfig_defaults.py
"""Regression tests for nested subconfig default merging."""

from pathlib import Path

from sec_nlp.pipelines.presets.analyze.config import AnalyzeConfig
from sec_nlp.pipelines.presets.chat.config import ChatSettings
from sec_nlp.pipelines.presets.events.config import EventsSettings
from sec_nlp.pipelines.presets.exb.config import ExhibitConfig
from sec_nlp.pipelines.presets.financials.config import FinancialsSettings
from sec_nlp.pipelines.presets.holdings.config import HoldingsSettings
from sec_nlp.pipelines.presets.insider.config import InsiderSettings
from sec_nlp.pipelines.presets.news.config import NewsSettings
from sec_nlp.pipelines.presets.retrieve.config import RetrieveSettings
from sec_nlp.pipelines.presets.retrieve.defaults import (
    DEFAULT_RETRIEVE_COLLECTION_NAME,
    DEFAULT_RETRIEVE_EMBEDDING_MODEL,
    DEFAULT_RETRIEVE_VECTOR_SIZE,
)
from sec_nlp.pipelines.presets.warranty.config import WarrantyConfig


def test_chat_partial_llm_override_preserves_pipeline_defaults(
    tmp_path: Path,
) -> None:
    config = ChatSettings.model_validate(
        {
            "email": "test@example.com",
            "symbols": ["MP"],
            "question": "What changed?",
            "dl_path": str(tmp_path / "downloads"),
            "out_path": str(tmp_path / "outputs"),
            "llm": {"model_name": "ministral-3:3b"},
        }
    )

    assert config.llm.model_name == "ministral-3:3b"
    assert config.llm.require_json is False
    assert config.llm.temperature == 0.1
    assert config.llm.max_new_tokens == 512
    assert config.collections == [DEFAULT_RETRIEVE_COLLECTION_NAME, "analyze"]
    assert config.vdb.collection_name == DEFAULT_RETRIEVE_COLLECTION_NAME
    assert config.vdb.embedding_model == DEFAULT_RETRIEVE_EMBEDDING_MODEL
    assert config.vdb.vector_size == DEFAULT_RETRIEVE_VECTOR_SIZE


def test_retrieve_partial_vdb_override_preserves_pipeline_defaults(
    tmp_path: Path,
) -> None:
    config = RetrieveSettings.model_validate(
        {
            "email": "test@example.com",
            "symbols": ["MP"],
            "queries": ["rare earth"],
            "dl_path": str(tmp_path / "downloads"),
            "out_path": str(tmp_path / "outputs"),
            "vdb": {"qdrant_location": ".qdrant/rems"},
        }
    )

    assert config.vdb.collection_name == DEFAULT_RETRIEVE_COLLECTION_NAME
    assert config.vdb.embedding_model == DEFAULT_RETRIEVE_EMBEDDING_MODEL
    assert config.vdb.search_type == "similarity"
    assert config.vdb.vector_size == DEFAULT_RETRIEVE_VECTOR_SIZE
    assert config.vdb.qdrant_location == ".qdrant/rems"


def test_exhibit_partial_vdb_override_preserves_pipeline_defaults(
    tmp_path: Path,
) -> None:
    config = ExhibitConfig.model_validate(
        {
            "email": "test@example.com",
            "symbols": ["CAT"],
            "dl_path": str(tmp_path / "downloads"),
            "out_path": str(tmp_path / "outputs"),
            "vdb": {"qdrant_location": ".qdrant/rems"},
        }
    )

    assert config.vdb.collection_name == "exhibit"
    assert config.vdb.embedding_model == "mxbai-embed-large"
    assert config.vdb.search_type == "cosine"
    assert config.vdb.vector_size == 1024
    assert config.vdb.qdrant_location == ".qdrant/rems"


def test_analyze_partial_vdb_override_preserves_pipeline_defaults(
    tmp_path: Path,
) -> None:
    config = AnalyzeConfig.model_validate(
        {
            "symbols": ["AAPL"],
            "dl_path": str(tmp_path / "downloads"),
            "out_path": str(tmp_path / "outputs"),
            "vdb": {"qdrant_location": ".qdrant/rems"},
        }
    )

    assert config.vdb.collection_name == "analyze"
    assert config.vdb.embedding_model == "bge-m3"
    assert config.vdb.search_type == "mmr"
    assert config.vdb.vector_size == 1024
    assert config.vdb.qdrant_location == ".qdrant/rems"


def test_all_pipeline_configs_include_semantic_chunking_subconfig() -> None:
    config_models = (
        AnalyzeConfig,
        ChatSettings,
        EventsSettings,
        ExhibitConfig,
        FinancialsSettings,
        HoldingsSettings,
        InsiderSettings,
        NewsSettings,
        RetrieveSettings,
        WarrantyConfig,
    )
    for config_model in config_models:
        assert "semantic_chunking" in config_model.model_fields


def test_retrieve_partial_semantic_override_preserves_defaults(
    tmp_path: Path,
) -> None:
    config = RetrieveSettings.model_validate(
        {
            "email": "test@example.com",
            "symbols": ["MP"],
            "queries": ["rare earth"],
            "dl_path": str(tmp_path / "downloads"),
            "out_path": str(tmp_path / "outputs"),
            "semantic_chunking": {"embedding_model": "qwen3-embedding:4b"},
        }
    )

    assert config.semantic_chunking.enabled is False
    assert config.semantic_chunking.embedding_model == "qwen3-embedding:4b"
    assert config.semantic_chunking.breakpoint_threshold_type == "percentile"
