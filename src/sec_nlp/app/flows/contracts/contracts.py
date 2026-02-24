# src/sec_nlp/app/flows/contracts/contracts.py
"""Flow contracts for exhibit/contract evidence and merged context packs."""

from pydantic import BaseModel, ConfigDict, Field

from .analysis import AnalysisEvidenceBundle
from .events import (
    EventTimelineBundle,
    FinancialStatementBundle,
    HeadlineBundle,
    OwnershipSignalBundle,
)
from .seed import FlowSeedBundle


class ContractEvidenceChunk(BaseModel):
    """Contract evidence snippet extracted from exhibit pipeline output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str | None = Field(
        default=None,
        description="Ticker symbol associated with the contract snippet.",
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
    exhibit_number: str | None = Field(
        default=None,
        description="Exhibit identifier (for example, 10.1).",
    )
    exhibit_category: str | None = Field(
        default=None,
        description="Derived exhibit category label.",
    )
    section_number: str | None = Field(
        default=None,
        description="Section number/heading marker when available.",
    )
    source: str | None = Field(
        default=None,
        description="Source file or URL for citation.",
    )
    score: float = Field(
        default=0.0,
        description="Optional ranking score for ordering evidence snippets.",
    )
    snippet: str = Field(
        default="",
        description="Contract text snippet used for evidence and citations.",
    )


class ContractEvidenceBundle(BaseModel):
    """Batch of contract evidence snippets for downstream flow stages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    upstream_pipeline: str = Field(
        default="exhibit",
        description="Pipeline that generated this contract evidence bundle.",
    )
    upstream_run_id: str = Field(
        description="Upstream run UUID for provenance.",
    )
    upstream_short_id: int | None = Field(
        default=None,
        description="Upstream short run ID when available.",
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols represented by contract evidence snippets.",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="Optional query list used to narrow contract candidates.",
    )
    chunks: list[ContractEvidenceChunk] = Field(
        default_factory=list,
        description="Contract evidence snippets extracted by EXB.",
    )


class ContextPack(BaseModel):
    """Merged multi-source context payload for future fan-in flow stages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: FlowSeedBundle | None = Field(
        default=None,
        description="Retrieve seed context for filing-grounded Q&A.",
    )
    analysis: AnalysisEvidenceBundle | None = Field(
        default=None,
        description="Analysis findings/evidence bundle.",
    )
    contracts: ContractEvidenceBundle | None = Field(
        default=None,
        description="Contract evidence bundle from exhibit pipeline.",
    )
    headlines: HeadlineBundle | None = Field(
        default=None,
        description="News headline context bundle.",
    )
    events: EventTimelineBundle | None = Field(
        default=None,
        description="Event timeline context bundle.",
    )
    financials: FinancialStatementBundle | None = Field(
        default=None,
        description="Financial statement signal bundle.",
    )
    ownership: OwnershipSignalBundle | None = Field(
        default=None,
        description="Ownership/insider signal bundle.",
    )
