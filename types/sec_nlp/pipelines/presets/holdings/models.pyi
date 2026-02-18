from typing import ClassVar, Literal

from pydantic import BaseModel

from sec_nlp.pipelines import BasePipelineResult as BasePipelineResult
from sec_nlp.types import JsonValue as JsonValue

class HoldingPosition(BaseModel):
    symbol: str
    accession_number: str
    form_type: str
    filed_date: str | None
    holding_index: int | None
    issuer: str | None
    title_of_class: str | None
    cusip: str | None
    value_thousands: int | None
    shares: int | None
    share_type: str | None
    investment_discretion: str | None
    other_manager: str | None
    voting_sole: int | None
    voting_shared: int | None
    voting_none: int | None
    source_file: str | None

class HoldingsDiff(BaseModel):
    symbol: str
    cusip: str
    issuer: str | None
    status: Literal["new", "exit", "increase", "decrease", "unchanged"]
    previous_accession: str | None
    current_accession: str | None
    previous_filed_date: str | None
    current_filed_date: str | None
    previous_shares: int | None
    current_shares: int | None
    share_change: int | None
    previous_value_thousands: int | None
    current_value_thousands: int | None
    value_change_thousands: int | None

class TopHolding(BaseModel):
    cusip: str
    issuer: str | None
    shares: int
    value_thousands: int
    portfolio_weight: float | None

class OwnershipSummary(BaseModel):
    symbol: str
    latest_accession: str | None
    latest_filed_date: str | None
    total_positions: int
    unique_cusips: int
    total_shares: int
    total_value_thousands: int
    concentration_hhi: float | None
    top_holdings: list[TopHolding]
    cusip_filter: str | None
    filtered_positions: int
    filtered_total_shares: int
    filtered_total_value_thousands: int

class HoldingsResult(BasePipelineResult):
    pipeline_type: ClassVar[Literal["holdings"]]
    symbols_processed: int
    positions_processed: int
    diffs_generated: int
    def summary_fields(self) -> dict[str, JsonValue]: ...
