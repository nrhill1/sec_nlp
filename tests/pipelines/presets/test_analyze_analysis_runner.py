# tests/pipelines/presets/test_analyze_analysis_runner.py
"""Tests for analyze analysis runner helpers."""

from pathlib import Path

from langchain_core.documents import Document
from langchain_core.runnables import Runnable, RunnableConfig

from sec_nlp.pipelines.presets.analyze.models import (
    AnalysisInput,
    AnalysisResult,
)
from sec_nlp.pipelines.presets.analyze.runnables.analysis import (
    AnalyzerRunnable,
)
from sec_nlp.types import JsonValue


def test_numeric_signal_detection_classmethod() -> None:
    assert AnalyzerRunnable._has_numeric_signal("Costs were $5 million")
    assert AnalyzerRunnable._has_numeric_signal(
        "Revenue grew 10% year over year"
    )
    assert not AnalyzerRunnable._has_numeric_signal("No digits here", "")
    assert not AnalyzerRunnable._has_numeric_signal(None)


class _CacheGraph(Runnable[AnalysisInput, AnalysisResult]):
    def __init__(self) -> None:
        self.batch_calls = 0

    def batch(
        self,
        inputs: list[AnalysisInput],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        *,
        return_exceptions: bool = False,
        **kwargs: JsonValue,
    ) -> list[AnalysisResult]:
        _ = config
        _ = kwargs
        if return_exceptions:
            raise ValueError("return_exceptions not supported")
        self.batch_calls += 1
        return [
            AnalysisResult(
                is_relevant=True,
                confidence_score=0.9,
                summary=f"summary-{idx}",
            )
            for idx in range(len(inputs))
        ]

    def invoke(
        self,
        input: AnalysisInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> AnalysisResult:
        _ = input
        _ = config
        _ = kwargs
        return AnalysisResult(
            is_relevant=True,
            confidence_score=0.9,
            summary="summary-single",
        )


def _make_docs() -> list[Document]:
    return [
        Document(
            page_content="Liquidity improved and debt declined.",
            metadata={
                "accession_number": "0000000001-26-000001",
                "search_query": "liquidity",
            },
        ),
        Document(
            page_content="Operating margin expanded in the quarter.",
            metadata={
                "accession_number": "0000000001-26-000002",
                "search_query": "margin expansion",
            },
        ),
    ]


def test_analyzer_runnable_llm_cache_reuses_results(tmp_path: Path) -> None:
    cache_path = tmp_path / "analyze_cache.json"
    graph = _CacheGraph()
    runner = AnalyzerRunnable(
        graph=graph,
        symbols=["AAPL"],
        llm_cache_enabled=True,
        llm_cache_file=cache_path,
        llm_cache_namespace="test-model",
        llm_cache_max_entries=100,
    )

    docs = _make_docs()
    first = runner.analyze_chunks("AAPL", docs)
    second = runner.analyze_chunks("AAPL", docs)

    assert len(first) == 2
    assert len(second) == 2
    assert graph.batch_calls == 1
    assert cache_path.exists()
