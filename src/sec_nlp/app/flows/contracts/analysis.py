# src/sec_nlp/app/flows/contracts/analysis.py
"""Flow contracts for retrieve/analyze evidence handoff."""

from pydantic import BaseModel, ConfigDict, Field

from .seed import FlowSeedChunk


class CandidateHitBundle(BaseModel):
    """Ranked retrieval candidates passed into downstream analysis stages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        default="retrieve",
        description="Pipeline that produced these candidate hits.",
    )
    upstream_run_id: str = Field(
        description="Upstream run UUID for provenance.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbol scope represented by these candidates.",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="Queries associated with candidate ranking.",
    )
    hits: list[FlowSeedChunk] = Field(
        default_factory=list,
        description="Ranked candidate hit snippets.",
    )


class AnalysisEvidenceBundle(BaseModel):
    """Analyze evidence summary passed to downstream answer stages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        default="analyze",
        description="Pipeline that produced this analysis evidence.",
    )
    upstream_run_id: str = Field(
        description="Upstream run UUID for provenance.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols represented in analysis evidence.",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="Analysis search queries, if configured.",
    )
    output_paths: list[str] = Field(
        default_factory=list,
        description="Output files containing detailed analysis artifacts.",
    )
    summary: str | None = Field(
        default=None,
        description="Optional summary line for downstream context composition.",
    )
