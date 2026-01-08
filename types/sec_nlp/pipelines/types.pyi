from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langchain_core.documents import Document

from sec_nlp.types import JsonValue

__all__ = [
    "DocumentList",
    "PathList",
    "QueryParam",
    "MetadataScalar",
    "MetadataValue",
    "MetadataMap",
    "MetadataRecord",
    "SourceMetadata",
    "FilingMetadata",
    "ProfilingMetadata",
    "TimerStats",
    "MemoryStats",
    "CustomMetricDict",
    "MetricsSummary",
    "AnalysisResultDict",
    "WarrantyExtractionDict",
    "WarrantyAggregateDict",
    "Exhibit10ResultDict",
]

type DocumentList = list[Document]
type PathList = list[Path]
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

class SourceMetadata(TypedDict, total=False):
    method: str
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
    accession_number: str
    form_type: str
    filing_date: str | None
    acceptance_date: str | None
    filing_year: int | None
    cik: str
    company_name: str

class ProfilingMetadata(TypedDict, total=False):
    duration_seconds: float
    memory_peak_mb: float
    memory_mean_mb: float
    phase_durations: dict[str, float]
    start_time: str
    end_time: str

class TimerStats(TypedDict):
    count: int
    total: float
    mean: float
    min_value: float
    max_value: float
    p50: float
    p95: float
    p99: float

class MemoryStats(TypedDict, total=False):
    samples: int
    mean_mb: float
    max_mb: float
    min_mb: float

class CustomMetricDict(TypedDict):
    name: str
    value: float
    unit: str
    tags: dict[str, str] | None

class MetricsSummary(TypedDict):
    pipeline: str
    start_time: float
    end_time: float | None
    total_duration_seconds: float
    counters: dict[str, int]
    gauges: dict[str, float]
    timers: dict[str, TimerStats]
    memory: MemoryStats
    custom_metrics: list[CustomMetricDict]

class AnalysisResultDict(TypedDict, total=False):
    is_relevant: bool
    confidence_score: float | None
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
    tags: list[str]
    sentiment: str | None
    severity: str | None
    forward_looking: bool
    evidence_spans: list[dict[str, str | int | float]]
    source_excerpt: str | None
    extracted_entities: dict[str, JsonValue]
    follow_up_questions: list[str]
    source_metadata: MetadataRecord
    matched_queries: list[dict[str, float | str]]
    raw_chunk: str
    error: str
    exception: str
    chunk_preview: str

class WarrantyExtractionDict(TypedDict, total=False):
    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None
    period: str | int | None
    period_end: str | None
    confidence: float | None
    source_metadata: SourceMetadata
    accession_number: str
    warranty_liability_from_xbrl: bool
    warranty_payout_from_xbrl: bool
    net_revenue_from_xbrl: bool
    error: str

class WarrantyAggregateDict(TypedDict, total=False):
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

class Exhibit10ResultDict(TypedDict, total=False):
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
