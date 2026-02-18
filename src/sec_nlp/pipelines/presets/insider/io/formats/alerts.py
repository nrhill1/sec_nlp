"""JSON/YAML payload writers for insider summaries and alerts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.output_io import write_json, write_yaml
from sec_nlp.types import JsonValue

from ...models import InsiderAlert, InsiderLedger, InsiderTransaction


class InsiderSummaryPayload(BaseModel):
    """Structured summary payload for insider pipeline outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_timestamp: str
    run_short_id: int | None = None
    run_id: str
    run_short_id_display: str
    symbol: str
    filings_processed: int
    transactions: list[InsiderTransaction] = Field(default_factory=list)
    ledgers: list[InsiderLedger] = Field(default_factory=list)
    net_buy_ratio: float | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class InsiderAlertsPayload(BaseModel):
    """Structured alert payload for insider pipeline outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_timestamp: str
    run_short_id: int | None = None
    run_id: str
    run_short_id_display: str
    symbol: str
    alerts: list[InsiderAlert] = Field(default_factory=list)


def write_insider_summary_json(path, payload: InsiderSummaryPayload) -> None:
    """Write insider summary payload to JSON."""
    write_json(path, payload, exclude_none=True)


def write_insider_summary_yaml(path, payload: InsiderSummaryPayload) -> None:
    """Write insider summary payload to YAML."""
    write_yaml(path, payload, exclude_none=True, sort_keys=False)


def write_insider_alerts_json(path, payload: InsiderAlertsPayload) -> None:
    """Write insider alerts payload to JSON."""
    write_json(path, payload, exclude_none=True)


def write_insider_alerts_yaml(path, payload: InsiderAlertsPayload) -> None:
    """Write insider alerts payload to YAML."""
    write_yaml(path, payload, exclude_none=True, sort_keys=False)
