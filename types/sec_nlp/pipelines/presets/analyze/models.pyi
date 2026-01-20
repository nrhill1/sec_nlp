from typing import ClassVar, Literal

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.pipelines import BasePipelineResult as BasePipelineResult
from sec_nlp.pipelines.base.result import SummaryFieldValue as SummaryFieldValue
from sec_nlp.pipelines.types import AnalysisResultDict as AnalysisResultDict
from sec_nlp.types import (
    JsonDict as JsonDict,
    JsonValue as JsonValue,
)

type EvidenceSpan = dict[str, str | int | float]
type EntityValue = JsonValue
type StringListInput = list[str] | str | int | float | None

class AnalysisInput(BaseModel):
    model_config: Incomplete
    chunk: str
    symbol: str
    matched_query: str | None
    matched_queries: list[str] | None
    context: str | None
    topic_hits: list[str] | None
    analysis_instructions: str | None

class AnalysisResult(BasePipelineResult):
    pipeline_type: ClassVar[Literal["analyze"]]
    model_config: Incomplete
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
    extracted_entities: dict[str, EntityValue]
    tags: list[str]
    evidence_spans: list[EvidenceSpan]
    source_excerpt: str | None
    severity: str | None
    sentiment: str | None
    forward_looking: bool
    follow_up_questions: list[str]
    def summary_fields(self) -> dict[str, SummaryFieldValue]: ...

class FilingInfo(BaseModel):
    model_config: Incomplete
    accession_number: str | None
    form_type: str | None
    acceptance_date: str | None
    filing_date: str | None

class ExecutiveSummary(BaseModel):
    model_config: Incomplete
    status: str
    total_chunks: int
    relevant_count: int
    average_confidence: float
    top_tags: list[str]
    top_topics: list[str]
    key_points: list[str]

class AnalysisDiagnostics(BaseModel):
    model_config: Incomplete
    chunks_analyzed: int
    chunks_successful: int
    chunks_failed: int
    chunks_relevant: int
    success_rate: float
    relevant_rate: float
    timings: dict[str, float]
    confidence_threshold: float

class Aggregates(BaseModel):
    model_config: Incomplete
    tag_frequency: dict[str, int]
    sentiment_breakdown: dict[str, int]
    sections_covered: dict[str, int]
    topic_hits_frequency: dict[str, int]
    impact_channel_frequency: dict[str, int]
    impact_horizon_frequency: dict[str, int]
    impact_direction_frequency: dict[str, int]
    impact_magnitude_frequency: dict[str, int]
    binding_status_frequency: dict[str, int]
    forward_looking_count: int

class AnalysisOutput(BaseModel):
    model_config: Incomplete
    symbol: str
    search_queries: list[str]
    filing: FilingInfo
    executive_summary: ExecutiveSummary
    aggregates: Aggregates
    diagnostics: AnalysisDiagnostics
    results: list[AnalysisResultDict]

class AnalyzeResult(BasePipelineResult):
    model_config: Incomplete
    pipeline_type: ClassVar[Literal["analyze"]]
    def summary_fields(self) -> dict[str, SummaryFieldValue]: ...
