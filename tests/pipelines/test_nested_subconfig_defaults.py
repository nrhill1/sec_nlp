"""Regression tests for nested subconfig default merging."""

from pathlib import Path

from sec_nlp.pipelines.presets.analyze import AnalyzeConfig
from sec_nlp.pipelines.presets.chat import ChatSettings
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings


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

    assert config.vdb.collection_name == "retrieve"
    assert config.vdb.search_type == "similarity"
    assert config.vdb.vector_size == 1024
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
