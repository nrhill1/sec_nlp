from pathlib import Path
from typing import ClassVar, Literal
from unittest.mock import Mock

from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableConfig
from rich.progress import Progress, TaskID

from sec_nlp.core.edgar.economic import EconomicSeries, MacroContext
from sec_nlp.pipelines.presets.analyze import (
    AnalysisInput,
    AnalysisResult,
    AnalyzeConfig,
    AnalyzePipeline,
    OutputFormatter,
    SearchConfig,
)
from sec_nlp.pipelines.presets.analyze.builders import (
    build_analysis_runner,
    build_output_formatter,
    build_preprocessor,
)
from sec_nlp.pipelines.presets.analyze.runnables.search import (
    SearchQueryResults,
    SearchRunnable,
)
from sec_nlp.pipelines.presets.analyze.types import (
    ChunkStats,
    PrefetchedSymbolData,
)
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataValue


class _TestAnalyzePipeline(AnalyzePipeline):
    """Lightweight pipeline for unit tests."""

    pipeline_type: ClassVar[Literal["analyze"]] = "analyze"
    description: ClassVar[str] = "Test analyze pipeline"

    def _build_components(self) -> None:
        self._callbacks = []
        self._graph = _FakeGraph()
        # Initialize required components with test-friendly versions
        self._preprocessor = build_preprocessor(
            config=self.config,
            section_extractor=None,
            topics=self.config.topics or self.config.keywords,
            embedder=None,
        )
        self._analysis_runner = build_analysis_runner(
            config=self.config,
            graph=self._graph,
            callbacks=self._callbacks,
            analysis_instructions="",
        )
        self._output_formatter = build_output_formatter(
            config=self.config,
            topics=self.config.topics or self.config.keywords,
        )
        self._search_runner = Mock(spec=SearchRunnable)


class _CachedSearchPipeline(AnalyzePipeline):
    """Pipeline stub that skips processing and uses cached search hits."""

    pipeline_type: ClassVar[Literal["analyze"]] = "analyze"
    description: ClassVar[str] = "Cached search pipeline"

    def _build_components(self) -> None:
        self._search_runner = Mock(spec=SearchRunnable)

    def _process_symbol(
        self,
        symbol: str,
        *,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
        prefetched: PrefetchedSymbolData | None = None,
    ) -> tuple[list[Path], ChunkStats]:
        self._search_results_by_query = {
            "cached-query": SearchQueryResults(filtered=[], total=0)
        }
        stats: ChunkStats = {}
        return [], stats


class _FakeGraph(Runnable[AnalysisInput, AnalysisResult]):
    """Graph that fails once then succeeds to exercise retries."""

    def __init__(self) -> None:
        self.batch_calls = 0

    def batch(
        self,
        inputs: list[AnalysisInput],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        *,
        return_exceptions: bool = False,
        **kwargs: MetadataValue,
    ) -> list[AnalysisResult]:
        if return_exceptions:
            raise ValueError("return_exceptions not supported in test stub")
        self.batch_calls += 1
        if self.batch_calls == 1:
            raise RuntimeError("Transient failure")
        return [
            AnalysisResult(
                is_relevant=True,
                confidence_score=0.8,
                summary=f"summary-{i}",
                key_points=[f"k{i}"],
            )
            for i in range(len(inputs))
        ]

    def invoke(
        self,
        input: AnalysisInput,
        config: RunnableConfig | None = None,
        **kwargs: MetadataValue,
    ) -> AnalysisResult:
        return AnalysisResult(
            is_relevant=True,
            confidence_score=0.8,
            summary="summary-0",
            key_points=["k0"],
        )


def _make_config(
    tmp_path: Path,
    *,
    top_k_chunks: int | None = None,
    adaptive_top_k_cap: int | None = None,
    llm_retry_attempts: int = 0,
    llm_retry_backoff: float = 0.0,
    batch_size: int = 2,
    min_chunk_length: int = 10,
    deduplicate_chunks: bool = False,
    macro_context: bool = False,
) -> AnalyzeConfig:
    return AnalyzeConfig(
        symbols=["AAPL"],
        out_path=tmp_path,
        dl_path=tmp_path,
        vector_mode="off",
        export_format="json",
        search=SearchConfig(queries=[]),
        collect_metrics=False,
        top_k_chunks=top_k_chunks,
        adaptive_top_k_cap=adaptive_top_k_cap,
        llm_retry_attempts=llm_retry_attempts,
        llm_retry_backoff=llm_retry_backoff,
        batch_size=batch_size,
        min_chunk_length=min_chunk_length,
        deduplicate_chunks=deduplicate_chunks,
        macro_context=macro_context,
    )


def _make_pipeline(
    tmp_path: Path,
    *,
    top_k_chunks: int | None = None,
    adaptive_top_k_cap: int | None = None,
    llm_retry_attempts: int = 0,
    llm_retry_backoff: float = 0.0,
    batch_size: int = 2,
    min_chunk_length: int = 10,
    deduplicate_chunks: bool = False,
    macro_context: bool = False,
) -> AnalyzePipeline:
    config = _make_config(
        tmp_path,
        top_k_chunks=top_k_chunks,
        adaptive_top_k_cap=adaptive_top_k_cap,
        llm_retry_attempts=llm_retry_attempts,
        llm_retry_backoff=llm_retry_backoff,
        batch_size=batch_size,
        min_chunk_length=min_chunk_length,
        deduplicate_chunks=deduplicate_chunks,
        macro_context=macro_context,
    )
    return _TestAnalyzePipeline(config=config)


def test_adaptive_top_k_applies_cap(tmp_path: Path) -> None:
    pipe = _make_pipeline(tmp_path, top_k_chunks=50, adaptive_top_k_cap=10)
    docs = [
        Document(
            page_content=f"text content value {i}",
            metadata={"topic_score": i},
        )
        for i in range(20)
    ]

    filtered = pipe._prepare_documents(docs)
    assert len(filtered) == 10, "adaptive_top_k_cap should cap selection to 10"


def test_coverage_metrics() -> None:
    """Test that OutputFormatter correctly calculates coverage metrics."""
    formatter = OutputFormatter(
        export_format="json",
        confidence_threshold=0.5,
        topics=["a"],
        include_raw_chunks=False,
    )
    filing_meta = {"accession_number": "123"}
    analysis_results: list[AnalysisResultDict] = [
        {"confidence_score": 0.9},
        {"error": "fail"},
        {"confidence_score": 0.6},
    ]
    relevant_results: list[AnalysisResultDict] = [
        {"confidence_score": 0.9, "key_points": [], "source_metadata": {}}
    ]

    output = formatter.build_output(
        "SYM", filing_meta, analysis_results, relevant_results
    )
    diag = output.diagnostics
    assert diag.chunks_analyzed == 3
    assert diag.chunks_successful == 2
    assert diag.chunks_failed == 1
    assert diag.chunks_relevant == 1


def test_output_includes_relationship_timeline() -> None:
    formatter = OutputFormatter(
        export_format="json",
        confidence_threshold=0.5,
        topics=["a"],
        include_raw_chunks=False,
    )
    filing_meta = {
        "accession_number": "0000000000-24-000001",
        "related_filings": [
            {
                "accession_number": "0000000000-24-000002",
                "relation_type": "amendment",
                "filed_date": "2024-01-01",
            }
        ],
    }

    output = formatter.build_output(
        "SYM", filing_meta, analysis_results=[], relevant_results=[]
    )

    assert "amendment" in output.relationship_timeline
    assert (
        output.relationship_timeline["amendment"][0].get("accession_number")
        == "0000000000-24-000002"
    )


def test_batch_retry_then_success(tmp_path: Path) -> None:
    pipe = _make_pipeline(tmp_path, llm_retry_attempts=1, llm_retry_backoff=0.0)
    docs = [Document(page_content="a"), Document(page_content="b")]
    batch = [
        AnalysisInput(symbol="SYM", chunk=d.page_content, context=None)
        for d in docs
    ]

    results = pipe._process_batch(batch, docs)
    assert len(results) == 2
    # First call fails, second succeeds
    graph = pipe._graph
    assert isinstance(graph, _FakeGraph)
    assert graph.batch_calls == 2


def test_run_uses_cached_search_results(tmp_path: Path) -> None:
    config = AnalyzeConfig(
        symbols=["AAPL"],
        out_path=tmp_path,
        dl_path=tmp_path,
        vector_mode="read",
        export_format="json",
        search=SearchConfig(queries=["cached-query"]),
        collect_metrics=False,
    )
    pipeline = _CachedSearchPipeline(config=config)

    pipeline.run()

    runner = pipeline._search_runner
    assert isinstance(runner, Mock)
    runner.export_results.assert_called_once()
    runner.run.assert_not_called()
    call = runner.export_results.call_args
    assert call.kwargs.get("cached") is True
    assert call.kwargs.get("queries") == ["cached-query"]


def test_build_macro_context_when_enabled(tmp_path: Path, monkeypatch) -> None:
    pipeline = _make_pipeline(tmp_path, macro_context=True)
    docs = [
        Document(
            page_content="macro doc",
            metadata={"filing_date": "2024-03-15"},
        )
    ]

    from sec_nlp.pipelines.presets.analyze import pipeline as pipeline_module

    def _mock_fetch_series(
        series_id: str,
        start_date: str = "",
        end_date: str = "",
    ) -> EconomicSeries:
        _ = start_date
        _ = end_date
        return EconomicSeries(
            series_id=series_id,
            description=series_id,
            observations=[("2024-03-01", 1.23)],
        )

    def _mock_align_to_filings(
        series: EconomicSeries,
        filing_dates: list[str],
    ) -> list[MacroContext]:
        filing_date = filing_dates[0]
        if series.series_id == "GDP":
            return [MacroContext(filing_date=filing_date, gdp_growth=1.23)]
        if series.series_id == "CPIAUCSL":
            return [MacroContext(filing_date=filing_date, cpi_yoy=1.23)]
        if series.series_id == "UNRATE":
            return [
                MacroContext(
                    filing_date=filing_date,
                    unemployment_rate=1.23,
                )
            ]
        if series.series_id == "FEDFUNDS":
            return [
                MacroContext(
                    filing_date=filing_date,
                    fed_funds_rate=1.23,
                )
            ]
        if series.series_id == "T10Y2Y":
            return [
                MacroContext(
                    filing_date=filing_date,
                    yield_spread_10y_2y=1.23,
                )
            ]
        return [MacroContext(filing_date=filing_date)]

    monkeypatch.setattr(pipeline_module, "fetch_series", _mock_fetch_series)
    monkeypatch.setattr(
        pipeline_module, "align_to_filings", _mock_align_to_filings
    )

    context = pipeline._build_macro_context(docs)

    assert context is not None
    assert "macro near 2024-03-15" in context
    assert "GDP=1.23" in context
    assert "UNRATE=1.23" in context


def test_run_search_and_analysis_skips_llm_when_search_analyze_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    from sec_nlp.pipelines.presets.analyze.runnables.analysis import (
        AnalyzerRunnable,
    )

    config = AnalyzeConfig(
        symbols=["AAPL"],
        out_path=tmp_path,
        dl_path=tmp_path,
        vector_mode="read",
        export_format="json",
        search=SearchConfig(queries=["warranty"], analyze=False),
        collect_metrics=False,
    )
    pipe = _TestAnalyzePipeline(config=config)
    pipe._vector_store = Mock()
    search_runner_raw = pipe._search_runner
    assert isinstance(search_runner_raw, Mock)
    search_runner = search_runner_raw
    search_runner.metadata_filters = {"symbol": ["AAPL"]}
    sample_docs = [
        Document(
            page_content="Sample filing text",
            metadata={
                "symbol": "AAPL",
                "accession_number": "0000000000-26-000001",
            },
        )
    ]
    search_runner.retrieve_hits_with_results.return_value = (
        sample_docs,
        {"warranty": SearchQueryResults(filtered=[], total=1)},
    )
    analyze_chunks = Mock(return_value=[])
    monkeypatch.setattr(AnalyzerRunnable, "analyze_chunks", analyze_chunks)

    analysis_results, docs_for_analysis = pipe._run_search_and_analysis(
        "AAPL",
        ["warranty"],
        {},
    )

    assert analysis_results == []
    assert docs_for_analysis == sample_docs
    analyze_chunks.assert_not_called()
