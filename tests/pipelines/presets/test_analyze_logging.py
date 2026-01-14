# tests/pipelines/presets/test_analyze_logging.py
"""Tests for analyze pipeline logging helpers."""

from unittest.mock import Mock

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

from sec_nlp.pipelines.presets.analyze import (
    AnalyzeConfig,
    AnalyzePipeline,
    OutputFormatter,
    SearchConfig,
    pipeline as analyze_pipeline,
)
from sec_nlp.pipelines.presets.analyze.config import EFTSConfig
from sec_nlp.pipelines.presets.analyze.market import MarketConfig
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataScalar


class _LoggingPipeline(AnalyzePipeline):
    pipeline_type = "analyze"
    description = "Logging test pipeline"

    def _build_components(self) -> None:
        docs = [
            Document(
                page_content="example chunk",
                metadata={
                    "accession_number": "0001",
                    "filing_date": "2024-01-01",
                },
            )
        ]
        analysis_results: list[AnalysisResultDict] = [
            {
                "is_relevant": True,
                "confidence_score": 0.9,
                "sentiment": "positive",
                "source_metadata": docs[0].metadata or {},
            }
        ]
        self._loader = Mock()
        self._loader.add_symbol = Mock()
        self._loader.load_documents = Mock(return_value=list(docs))
        self._loader.last_meta = {"relationships": {}}
        self._loader.company_name = "Test Co"

        self._preprocessor = Mock()
        self._preprocessor.chunk_and_prepare = Mock(return_value=list(docs))

        self._vector_indexer = Mock()
        self._vector_indexer.index = Mock()

        self._search_runner = Mock()
        self._search_runner.retrieve_hits_with_results = Mock(
            return_value=(list(docs), {})
        )

        self._analysis_runner = Mock()
        self._analysis_runner.analyze_chunks = Mock(
            return_value=analysis_results
        )

        self._output_formatter = OutputFormatter(
            export_format=self.config.export_format,
            confidence_threshold=self.config.confidence_threshold,
            topics=self.config.topics or self.config.keywords,
            include_raw_chunks=self.config.include_raw_chunks,
        )
        self._vector_store = Mock(spec=QdrantVectorStore)


def test_vector_search_logs_chunk_stats(tmp_path, monkeypatch) -> None:
    labels = []

    def fake_log_chunk_length_stats(
        *,
        label: MetadataScalar = None,
        symbol: MetadataScalar = None,
        accession: MetadataScalar = None,
        docs: list[Document],
        keyword_field: MetadataScalar = None,
        prefix_color: MetadataScalar = None,
    ) -> None:
        _ = symbol
        _ = accession
        _ = docs
        _ = keyword_field
        _ = prefix_color
        labels.append(label)

    monkeypatch.setattr(
        analyze_pipeline, "log_chunk_length_stats", fake_log_chunk_length_stats
    )

    config = AnalyzeConfig(
        symbols=["ACME"],
        out_path=tmp_path,
        dl_path=tmp_path,
        vector_mode="read",
        export_format="json",
        search=SearchConfig(queries=["market demand shift"]),
        efts=EFTSConfig(enabled=False),
        market=MarketConfig(enabled=False),
        validate_config=False,
        collect_metrics=False,
    )

    pipeline = _LoggingPipeline(config=config)
    pipeline._process_symbol("ACME")

    assert "vector" in labels
