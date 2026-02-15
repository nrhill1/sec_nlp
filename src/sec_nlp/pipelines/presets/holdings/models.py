"""Data models for holdings pipeline."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines import BasePipelineResult
from sec_nlp.types import JsonValue


class HoldingPosition(BaseModel):
    """Normalized 13F position entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    accession_number: str
    form_type: str
    filed_date: str | None = None
    holding_index: int | None = None
    issuer: str | None = None
    title_of_class: str | None = None
    cusip: str | None = None
    value_thousands: int | None = None
    shares: int | None = None
    share_type: str | None = None
    investment_discretion: str | None = None
    other_manager: str | None = None
    voting_sole: int | None = None
    voting_shared: int | None = None
    voting_none: int | None = None
    source_file: str | None = None


class HoldingsDiff(BaseModel):
    """Quarter-over-quarter position change for one CUSIP."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    cusip: str
    issuer: str | None = None
    status: Literal["new", "exit", "increase", "decrease", "unchanged"]
    previous_accession: str | None = None
    current_accession: str | None = None
    previous_filed_date: str | None = None
    current_filed_date: str | None = None
    previous_shares: int | None = None
    current_shares: int | None = None
    share_change: int | None = None
    previous_value_thousands: int | None = None
    current_value_thousands: int | None = None
    value_change_thousands: int | None = None


class TopHolding(BaseModel):
    """Top holding entry for summary output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cusip: str
    issuer: str | None = None
    shares: int = 0
    value_thousands: int = 0
    portfolio_weight: float | None = None


class OwnershipSummary(BaseModel):
    """Aggregate holdings metrics for latest filing window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    latest_accession: str | None = None
    latest_filed_date: str | None = None
    total_positions: int = 0
    unique_cusips: int = 0
    total_shares: int = 0
    total_value_thousands: int = 0
    concentration_hhi: float | None = None
    top_holdings: list[TopHolding] = Field(default_factory=list)
    cusip_filter: str | None = None
    filtered_positions: int = 0
    filtered_total_shares: int = 0
    filtered_total_value_thousands: int = 0


class HoldingsResult(BasePipelineResult):
    """Result model for holdings pipeline."""

    pipeline_type: ClassVar[Literal["holdings"]] = "holdings"

    model_config = ConfigDict(frozen=True, extra="ignore")

    symbols_processed: int = Field(
        default=0,
        description="Number of symbols processed by the pipeline.",
    )
    positions_processed: int = Field(
        default=0,
        description="Total holdings positions parsed across all symbols.",
    )
    diffs_generated: int = Field(
        default=0,
        description="Total quarter-over-quarter diff records generated.",
    )

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["symbols_processed"] = self.symbols_processed
        fields["positions_processed"] = self.positions_processed
        fields["diffs_generated"] = self.diffs_generated
        return fields
