from pydantic import BaseModel

from sec_nlp.types import JsonValue as JsonValue

from ...models import (
    InsiderAlert as InsiderAlert,
    InsiderLedger as InsiderLedger,
    InsiderTransaction as InsiderTransaction,
)

class InsiderSummaryPayload(BaseModel):
    symbol: str
    filings_processed: int
    transactions: list[InsiderTransaction]
    ledgers: list[InsiderLedger]
    net_buy_ratio: float | None
    metadata: dict[str, JsonValue]

class InsiderAlertsPayload(BaseModel):
    symbol: str
    alerts: list[InsiderAlert]

def write_insider_summary_json(
    path, payload: InsiderSummaryPayload
) -> None: ...
def write_insider_summary_yaml(
    path, payload: InsiderSummaryPayload
) -> None: ...
def write_insider_alerts_json(path, payload: InsiderAlertsPayload) -> None: ...
def write_insider_alerts_yaml(path, payload: InsiderAlertsPayload) -> None: ...
