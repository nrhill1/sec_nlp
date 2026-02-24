# src/sec_nlp/app/flows/contracts/seed.py
"""Canonical seeded-context contracts for flow stage handoff."""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class FlowSeedChunk(BaseModel):
    """Minimal filing chunk payload reused by retrieve and chat flow stages."""

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
    """Canonical seeded context bundle shared by retrieve and chat."""

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
        """Backward-compatible accessor for legacy retrieve bridge fields."""
        return self.upstream_run_id

    @property
    def run_short_id(self) -> int | None:
        """Backward-compatible accessor for legacy retrieve bridge fields."""
        return self.upstream_short_id
