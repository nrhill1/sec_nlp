# src/sec_nlp/pipelines/presets/analyze/__init__.py
"""Generalized document analysis pipeline with semantic search."""

from .callbacks import TracingCallbackHandler
from .config import AnalyzeConfig, SearchConfig
from .models import (
    Aggregates,
    AnalysisDiagnostics,
    AnalysisInput,
    AnalysisOutput,
    AnalysisResult,
    AnalyzeResult,
    ExecutiveSummary,
    FilingInfo,
)
from .outputs import OutputFormatter
from .pipeline import AnalyzePipeline

__all__: tuple[str, ...] = (
    "Aggregates",
    "AnalysisDiagnostics",
    "AnalysisInput",
    "AnalysisOutput",
    "AnalysisResult",
    "AnalyzeConfig",
    "AnalyzePipeline",
    "AnalyzeResult",
    "ExecutiveSummary",
    "FilingInfo",
    "OutputFormatter",
    "SearchConfig",
    "TracingCallbackHandler",
)
