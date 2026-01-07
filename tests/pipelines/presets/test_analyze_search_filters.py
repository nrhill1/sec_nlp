# tests/pipelines/presets/test_analyze_search_filters.py
"""Tests for analyze pipeline search filters and metadata-based outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, Literal
from unittest.mock import Mock

from langchain_qdrant import QdrantVectorStore
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from sec_nlp.pipelines.metadata.filters import MetadataFilters
from sec_nlp.pipelines.presets.analyze import (
    AnalyzeConfig,
    AnalyzePipeline,
    OutputFormatter,
    SearchConfig,
)
from sec_nlp.pipelines.types import AnalysisResultDict


class _TestAnalyzePipeline(AnalyzePipeline):
    """Lightweight pipeline for unit tests."""

    pipeline_type: ClassVar[Literal["analyze"]] = "analyze"
    description: ClassVar[str] = "Test analyze pipeline"

    def _build_components(self) -> None:
        self._output_formatter = OutputFormatter(
            export_format=self.config.export_format,
            confidence_threshold=self.config.confidence_threshold,
            topics=self.config.topics or self.config.keywords,
            include_raw_chunks=self.config.include_raw_chunks,
        )
        self._vector_store = Mock(spec=QdrantVectorStore)


def _make_config(
    tmp_path: Path,
    *,
    metadata_filters: MetadataFilters | None = None,
    with_queries: bool = True,
) -> AnalyzeConfig:
    queries = ["executive compensation clawback"] if with_queries else []
    filters: MetadataFilters = (
        metadata_filters if metadata_filters is not None else {}
    )
    search = SearchConfig(
        queries=queries,
        limit=5,
        score_threshold=0.7,
        metadata_filters=filters,
    )
    return AnalyzeConfig(
        symbols=["AAPL"],
        out_path=tmp_path,
        dl_path=tmp_path,
        vector_mode="read" if with_queries else "off",
        export_format="json",
        search=search,
        validate_config=False,
        collect_metrics=False,
    )


def test_retrieve_search_hits_passes_metadata_filter(
    tmp_path: Path,
) -> None:
    filters: MetadataFilters = {
        "symbol": ["AAPL", "MSFT"],
        "form_type": ["10-K"],
    }
    config = _make_config(tmp_path, metadata_filters=filters)
    pipeline = _TestAnalyzePipeline(config=config)
    vector_store = pipeline._vector_store
    assert isinstance(vector_store, Mock)
    vector_store.similarity_search_with_score.return_value = []

    pipeline._retrieve_search_hits()

    call_args = vector_store.similarity_search_with_score.call_args
    assert call_args is not None
    _args, kwargs = call_args
    filter_arg = kwargs.get("filter")
    assert isinstance(filter_arg, Filter)
    must_conditions = filter_arg.must
    assert isinstance(must_conditions, list)

    symbol_condition: FieldCondition | None = None
    form_condition: FieldCondition | None = None
    for condition in must_conditions:
        if isinstance(condition, FieldCondition) and condition.key == "symbol":
            symbol_condition = condition
        if (
            isinstance(condition, FieldCondition)
            and condition.key == "form_type"
        ):
            form_condition = condition

    assert symbol_condition is not None
    assert isinstance(symbol_condition.match, MatchAny)
    assert set(symbol_condition.match.any) == {"AAPL", "MSFT"}

    assert form_condition is not None
    assert isinstance(form_condition.match, MatchValue)
    assert form_condition.match.value == "10-K"


def test_write_results_uses_metadata_symbol(tmp_path: Path) -> None:
    config = _make_config(tmp_path, with_queries=False)
    pipeline = _TestAnalyzePipeline(config=config)

    analysis_results: list[AnalysisResultDict] = [
        {
            "is_relevant": True,
            "confidence_score": 0.92,
            "summary": "test",
            "source_metadata": {
                "symbol": "MSFT",
                "accession_number": "0000000000-00-000000",
            },
        }
    ]

    output_files = pipeline._write_results(
        symbol="AAPL",
        filing_meta={"accession_number": "0000000000-00-000000"},
        analysis_results=analysis_results,
        relevant_results=analysis_results,
    )

    assert output_files
    output_path = output_files[0]
    with open(output_path, encoding="utf-8") as handle:
        data = json.load(handle)

    assert data["symbol"] == "MSFT"
    assert "MSFT" in output_path.parts
