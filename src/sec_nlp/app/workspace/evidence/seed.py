# src/sec_nlp/app/workspace/evidence/seed.py
"""Canonical seeded-context contracts for flow stage handoff."""

from dataclasses import dataclass

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class FlowSeedChunk(BaseModel):
    """Normalized filing snippet contract for stage-to-stage evidence transfer.

    This model is the low-friction boundary object between retrieval/ranking
    stages and downstream consumers (chat, analyze, or future fan-in stages).
    It keeps only provenance + snippet data needed for citation and ordering.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str = Field(
        default="retrieve",
        description="Source collection label for citation provenance.",
    )
    score: float = Field(
        default=0.0,
        description="Precomputed retrieval score used for ordering.",
    )
    symbol: str | None = Field(
        default=None,
        description="Associated symbol if available.",
    )
    accession_number: str | None = Field(
        default=None,
        description="SEC accession identifier.",
    )
    form_type: str | None = Field(
        default=None,
        description="SEC form type for the originating filing.",
    )
    filed_date: str | None = Field(
        default=None,
        description="Filing date in YYYY-MM-DD format.",
    )
    source: str | None = Field(
        default=None,
        description="Source URL for the citation.",
    )
    snippet: str = Field(
        default="",
        description="Snippet text used for prompt context and citations.",
    )


class FlowSeedBundle(BaseModel):
    """Run-scoped seeded evidence envelope emitted by retrieval-style stages.

    Use this as the canonical upstream context object when a downstream stage
    needs query/symbol provenance and a compact set of ranked filing snippets.
    Chat can pair this with `FlowRetrievedChunk` tuples for zero-copy context.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        default="retrieve",
        description="Pipeline that generated this seeded context.",
    )
    upstream_run_id: str = Field(
        validation_alias=AliasChoices("upstream_run_id", "run_id"),
        description="Upstream run UUID for provenance.",
    )
    upstream_short_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("upstream_short_id", "run_short_id"),
        description="Upstream short run ID when available.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols represented in seeded chunks.",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="Upstream query list used to produce chunks.",
    )
    chunks: list[FlowSeedChunk] = Field(
        default_factory=list,
        description="Seeded chunks available for answer generation.",
    )

    @property
    def run_id(self) -> str:
        """Expose `upstream_run_id` under the legacy `run_id` bridge name."""
        return self.upstream_run_id

    @property
    def run_short_id(self) -> int | None:
        """Expose `upstream_short_id` under the legacy bridge field name."""
        return self.upstream_short_id


@dataclass(slots=True, frozen=True)
class FlowRetrievedChunk:
    """Chat-native chunk record for zero-copy flow handoff.

    This dataclass intentionally mirrors chat's internal retrieval shape so the
    runner can pass tuples by reference without model conversion or revalidation.
    """

    collection: str
    score: float
    symbol: str | None
    accession_number: str | None
    form_type: str | None
    filed_date: str | None
    source: str | None
    snippet: str
    vector: list[float] | None = None
