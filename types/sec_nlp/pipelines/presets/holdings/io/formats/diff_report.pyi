from pydantic import BaseModel

from sec_nlp.types import JsonValue as JsonValue

from ...models import (
    HoldingPosition as HoldingPosition,
    HoldingsDiff as HoldingsDiff,
    OwnershipSummary as OwnershipSummary,
)

class HoldingsSummaryPayload(BaseModel):
    run_timestamp: str
    run_short_id: int | None
    run_id: str
    run_short_id_display: str
    symbol: str
    filings_processed: int
    positions: list[HoldingPosition]
    summary: OwnershipSummary
    metadata: dict[str, JsonValue]

class HoldingsDiffPayload(BaseModel):
    run_timestamp: str
    run_short_id: int | None
    run_id: str
    run_short_id_display: str
    symbol: str
    diffs: list[HoldingsDiff]

def write_holdings_summary_json(
    path, payload: HoldingsSummaryPayload
) -> None: ...
def write_holdings_summary_yaml(
    path, payload: HoldingsSummaryPayload
) -> None: ...
def write_holdings_diff_json(path, payload: HoldingsDiffPayload) -> None: ...
def write_holdings_diff_yaml(path, payload: HoldingsDiffPayload) -> None: ...
