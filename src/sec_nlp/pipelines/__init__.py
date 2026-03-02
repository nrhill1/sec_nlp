# src/sec_nlp/pipelines/__init__.py
"""Pipeline implementations."""

from .base import (  # noqa: I001
    BasePipelineSettings,
    BasePipeline,
    BasePipelineResult,
    PipelineStageRunnable,
    PipelineValidator,
    ValidationReport,
    ValidationResult,
    validate_pipeline,
)
from .llm import LLMConfig
from .observability import (
    PipelineMetrics,
    PipelineProfiler,
    track_pipeline_metrics,
)
from .types import (
    AnalysisResultDict,
    DocumentList,
    ExhibitResultDict,
    FilingMetadata,
    PathList,
    SourceMetadata,
    WarrantyAggregateDict,
    WarrantyExtractionDict,
)
from .vector import VectorConfig

__all__: tuple[str, ...] = (
    # Base
    "BasePipeline",
    "BasePipelineResult",
    "PipelineStageRunnable",
    # Config
    "BasePipelineSettings",
    "LLMConfig",
    "VectorConfig",
    "DocumentList",
    "PathList",
    # TypedDicts
    "SourceMetadata",
    "FilingMetadata",
    "AnalysisResultDict",
    "WarrantyExtractionDict",
    "WarrantyAggregateDict",
    "ExhibitResultDict",
    # Validation
    "validate_pipeline",
    "PipelineValidator",
    "ValidationReport",
    "ValidationResult",
    # Metrics
    "PipelineMetrics",
    "track_pipeline_metrics",
    # Profiling
    "PipelineProfiler",
)
