# src/sec_nlp/pipelines/types.py
"""Common type aliases and TypedDicts for pipelines.

This module centralizes type definitions to reduce verbosity, provide
a single source of truth, and enable runtime type safety.
"""

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langchain_core.documents import Document

from sec_nlp.types import JsonValue

# =============================================================================
# Common Collection Type Aliases
# =============================================================================

type DocumentList = list[Document]
type PathList = list[Path]

# SQL query parameter types
type QueryParam = str | int | float | datetime | None
type MetadataScalar = str | int | float | bool | None
type MetadataValue = (
    MetadataScalar
    | list[MetadataScalar]
    | dict[str, MetadataScalar]
    | list[dict[str, MetadataScalar]]
    | dict[str, list[dict[str, MetadataScalar]]]
)
type MetadataMap = Mapping[str, MetadataValue]
type MetadataRecord = dict[str, MetadataValue]


# =============================================================================
# Shared Metadata TypedDicts
# =============================================================================


class SourceMetadata(TypedDict, total=False):
    """Metadata attached to analysis results indicating provenance."""

    method: str  # e.g., "xbrl_facts", "llm"
    symbol: str
    accession_number: str
    period: str | int | None
    period_end: str | None
    fiscal_year: str | int | None
    section_number: str | None
    chunk_index: int
    topic_hits: list[str]
    topic_score: int
    simhash: int
    xbrl_conflicts: list[str]
    xbrl_values_seen: dict[str, list[dict[str, str | int | float | None]]]


class FilingMetadata(TypedDict, total=False):
    """Metadata describing an SEC filing."""

    accession_number: str
    form_type: str
    filing_date: str | None
    acceptance_date: str | None
    filing_year: int | None
    cik: str
    company_name: str


class ProfilingMetadata(TypedDict, total=False):
    """Metadata for pipeline profiling."""

    duration_seconds: float
    memory_peak_mb: float
    memory_mean_mb: float
    phase_durations: dict[str, float]
    start_time: str
    end_time: str


class TimerStats(TypedDict):
    """Statistics for timer metrics."""

    count: int
    total: float
    mean: float
    min_value: float
    max_value: float
    p50: float
    p95: float
    p99: float


class MemoryStats(TypedDict, total=False):
    """Memory usage statistics."""

    samples: int
    mean_mb: float
    max_mb: float
    min_mb: float


class CustomMetricDict(TypedDict):
    """Custom metric data point."""

    name: str
    value: float
    unit: str
    tags: dict[str, str] | None


class MetricsSummary(TypedDict):
    """Summary of pipeline metrics."""

    pipeline: str
    start_time: float
    end_time: float | None
    total_duration_seconds: float
    counters: dict[str, int]
    gauges: dict[str, float]
    timers: dict[str, TimerStats]
    memory: MemoryStats
    custom_metrics: list[CustomMetricDict]


# =============================================================================
# Analysis Pipeline TypedDicts
# =============================================================================


class AnalysisResultDict(TypedDict, total=False):
    """Result dict from LLM analysis of a document chunk."""

    # Core fields
    is_relevant: bool
    confidence_score: float | None
    rank: int
    confidence_bucket: str
    summary: str | None
    key_points: list[str]
    reasoning: str | None
    query_match_terms: list[str]
    missing_query_terms: list[str]
    binding_status: str | None
    contingencies: list[str]
    impact_channels: list[str]
    impact_direction: str | None
    impact_magnitude: str | None
    impact_horizon: str | None
    impact_confidence: float | None
    impact_rationale: str | None

    # Classification
    tags: list[str]
    sentiment: str | None
    severity: str | None
    forward_looking: bool

    # Evidence
    evidence_spans: list[dict[str, str | int | float]]
    source_excerpt: str | None
    extracted_entities: dict[str, JsonValue]
    follow_up_questions: list[str]

    # Provenance
    source_metadata: MetadataRecord
    matched_queries: list[dict[str, float | str]]
    raw_chunk: str

    # Error handling
    error: str
    exception: str
    chunk_preview: str


# =============================================================================
# Warranty Pipeline TypedDicts
# =============================================================================


class WarrantyExtractionDict(TypedDict, total=False):
    """Result dict from warranty data extraction."""

    # Core financial fields
    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None

    # Period info
    period: str | int | None
    period_end: str | None

    # Confidence and provenance
    confidence: float | None
    source_metadata: SourceMetadata
    accession_number: str

    # XBRL tracking flags
    warranty_liability_from_xbrl: bool
    warranty_payout_from_xbrl: bool
    net_revenue_from_xbrl: bool

    # Error handling
    error: str


class WarrantyAggregateDict(TypedDict, total=False):
    """Aggregated warranty record for a period."""

    symbol: str
    period: str | None
    period_end: str | None
    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None
    confidence: float
    accessions: set[str | None]
    source_flags: set[str]
    warranty_liability_from_xbrl: bool
    warranty_payout_from_xbrl: bool
    net_revenue_from_xbrl: bool
    xbrl_conflicted_fields: set[str]


# =============================================================================
# Exhibit 10 Pipeline TypedDicts
# =============================================================================


class Exhibit10ResultDict(TypedDict, total=False):
    """Result dict from Exhibit 10 contract analysis."""

    is_relevant: bool
    relevance_score: float | None
    contract_type: str | None
    contract_category: str | None
    parties: list[str]
    supplier_names: list[str]
    key_terms: list[str]
    obligations: list[str]
    summary: str | None
    has_exclusivity: bool
    has_aftermarket_provisions: bool
    has_pricing_at_cost: bool
    reasoning: str | None
    source_metadata: SourceMetadata
    error: str


# =============================================================================
# Exports
# =============================================================================

__all__: tuple[str, ...] = (
    # Collection types
    "DocumentList",
    "PathList",
    "QueryParam",
    "MetadataScalar",
    "MetadataValue",
    "MetadataMap",
    "MetadataRecord",
    # Shared metadata
    "SourceMetadata",
    "FilingMetadata",
    "ProfilingMetadata",
    # Metrics
    "TimerStats",
    "MemoryStats",
    "CustomMetricDict",
    "MetricsSummary",
    # Analysis pipeline
    "AnalysisResultDict",
    # Warranty pipeline
    "WarrantyExtractionDict",
    "WarrantyAggregateDict",
    # Exhibit 10 pipeline
    "Exhibit10ResultDict",
)
