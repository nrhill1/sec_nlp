"""Observability helpers for pipelines (metrics, profiling, telemetry)."""

from .metrics import PipelineMetrics, track_pipeline_metrics
from .profiling import PipelineProfiler
from .run_registry import RunRecord, RunRegistry, get_registry
from .telemetry import (
    log_chunk_length_stats,
    log_document_metadata,
    log_exhibit_stats,
    log_filter_stats,
    log_llm_inputs,
)

__all__: tuple[str, ...] = (
    "PipelineMetrics",
    "track_pipeline_metrics",
    "PipelineProfiler",
    "RunRecord",
    "RunRegistry",
    "get_registry",
    "log_chunk_length_stats",
    "log_document_metadata",
    "log_exhibit_stats",
    "log_filter_stats",
    "log_llm_inputs",
)
