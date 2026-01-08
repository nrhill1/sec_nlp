# src/sec_nlp/pipelines/presets/analyze/__init__.py
"""Generalized document analysis pipeline with semantic search."""

from .config import AnalyzeConfig, SearchConfig
from .io.outputs import OutputFormatter
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
from .pipeline import AnalyzePipeline
from .steps.analysis.callbacks import TracingCallbackHandler

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
