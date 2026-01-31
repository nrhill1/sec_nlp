# src/sec_nlp/pipelines/presets/analyze/runnables/chain.py
"""Runnable composition helpers for the analyze pipeline."""

from __future__ import annotations

from langchain_core.runnables import Runnable

from sec_nlp.pipelines.types import AnalysisResultDict

from .analysis import AnalyzerRunnable
from .search import SearchRetrieveInput, SearchRunnable


def build_search_analysis_chain(
    *,
    search_runner: SearchRunnable,
    analyzer: AnalyzerRunnable,
) -> Runnable[SearchRetrieveInput, list[AnalysisResultDict]]:
    """Compose search retrieval + analysis into a runnable sequence."""
    return search_runner | analyzer
