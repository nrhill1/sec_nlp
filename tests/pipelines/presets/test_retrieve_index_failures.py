# tests/pipelines/presets/test_retrieve_index_failures.py
"""Test truthful completion for explicitly requested vector indexing.

Backend and embedding failures must fail the requested index operation, while
ordinary lexical retrieval remains usable without optional vector components.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_ollama import OllamaEmbeddings
from qdrant_client import QdrantClient

from sec_nlp.pipelines.presets.retrieve.config import RetrieveSettings
from sec_nlp.pipelines.presets.retrieve.models import RetrievalHit
from sec_nlp.pipelines.presets.retrieve.pipeline import RetrievePipeline


def _settings(
    tmp_path: Path, *, index_results: bool = True
) -> RetrieveSettings:
    """Build a local single-symbol retrieval operation with explicit index intent."""
    return RetrieveSettings(
        symbols=["AAPL"],
        queries=["supply"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        download_missing=False,
        incremental=False,
        index_results=index_results,
        embedding_cache=False,
    )


def _hit() -> RetrievalHit:
    """Return a hydrated source record suitable for vector indexing."""
    return RetrievalHit(
        symbol="AAPL",
        query="supply",
        accession_number="0001234567-26-000001",
        form_type="10-K",
        filed_date="2026-01-31",
        company_name="Example Company",
        cik="0001234567",
        score=1.0,
        edgar_url="https://www.sec.gov/example",
        snippet="A supply agreement.",
        chunk_index=0,
    )


@pytest.mark.parametrize("missing_component", ["embedding", "backend"])
def test_requested_index_fails_before_source_collection_when_components_missing(
    tmp_path: Path,
    missing_component: str,
) -> None:
    """Report component failures before collecting filings or emitting results."""
    with (
        patch(
            "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
            return_value=(MagicMock(spec=OllamaEmbeddings), 2),
        ) as embeddings,
        patch(
            "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
            return_value=MagicMock(spec=QdrantClient),
        ) as backend,
        patch(
            "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search"
        ) as search,
    ):
        if missing_component == "embedding":
            embeddings.side_effect = ModuleNotFoundError(
                "langchain_ollama is absent", name="langchain_ollama"
            )
        else:
            backend.side_effect = RuntimeError("backend unavailable")
        result = RetrievePipeline(config=_settings(tmp_path)).run()
    search.assert_not_called()
    assert not result.success
    assert result.outputs == []
    assert (
        result.error is not None
        and "Requested indexing cannot start" in result.error
    )


@pytest.mark.parametrize("failure_method", ["collection_exists", "upsert"])
def test_backend_index_failure_becomes_failed_pipeline_result(
    tmp_path: Path,
    failure_method: str,
) -> None:
    """Never report an exported or successful index when a backend rejects work."""
    backend = MagicMock(spec=QdrantClient)
    backend.collection_exists.return_value = True
    if failure_method == "collection_exists":
        backend.collection_exists.side_effect = RuntimeError(
            "collection lookup rejected"
        )
    else:
        backend.upsert.side_effect = RuntimeError("upsert rejected")
    hits = [_hit()]
    with (
        patch(
            "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
            return_value=(MagicMock(spec=OllamaEmbeddings), 2),
        ),
        patch(
            "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
            return_value=backend,
        ),
        patch(
            "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search",
            return_value={"supply": []},
        ),
        patch.object(RetrievePipeline, "_rank_hits", return_value=hits),
        patch.object(
            RetrievePipeline, "_download_and_chunk_hits", return_value=hits
        ),
        patch(
            "sec_nlp.pipelines.presets.retrieve.steps.index.embed_texts_with_cache",
            return_value=[[0.2, 0.8]],
        ),
    ):
        result = RetrievePipeline(config=_settings(tmp_path)).run()
    assert not result.success
    assert result.outputs == []
    assert result.error is not None and "rejected" in result.error


def test_ordinary_retrieval_does_not_require_vector_components(
    tmp_path: Path,
) -> None:
    """Complete lexical retrieval without attempting optional component setup."""
    with (
        patch(
            "sec_nlp.pipelines.vector.config.VectorConfig.setup_embedding_model",
            side_effect=ImportError("no embeddings"),
        ) as embeddings,
        patch(
            "sec_nlp.pipelines.vector.config.VectorConfig.setup_qdrant_client",
            side_effect=ImportError("no vector backend"),
        ) as backend,
        patch(
            "sec_nlp.pipelines.presets.retrieve.pipeline.run_candidate_search",
            return_value={"supply": []},
        ),
    ):
        result = RetrievePipeline(
            config=_settings(tmp_path, index_results=False)
        ).run()
    embeddings.assert_not_called()
    backend.assert_not_called()
    assert result.success
