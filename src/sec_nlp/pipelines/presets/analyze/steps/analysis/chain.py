# src/sec_nlp/pipelines/presets/analyze/steps/analysis/chain.py
"""Runnable composition helpers for the analyze pipeline."""

from __future__ import annotations

from langchain_core.runnables import Runnable

from sec_nlp.pipelines.types import AnalysisResultDict

from ..search.vector_search import SearchRetrieveInput, SearchRunnable
from .analysis_runner import AnalyzerRunnable


def build_search_analysis_chain(
    *,
    search_runner: SearchRunnable,
    analyzer: AnalyzerRunnable,
) -> Runnable[SearchRetrieveInput, list[AnalysisResultDict]]:
    """Compose search retrieval + analysis into a runnable sequence."""
    return search_runner | analyzer
