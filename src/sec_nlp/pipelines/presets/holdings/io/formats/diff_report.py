"""JSON/YAML payload writers for holdings summary and diff reports."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.output_io import write_json, write_yaml
from sec_nlp.types import JsonValue

from ...models import HoldingPosition, HoldingsDiff, OwnershipSummary


class HoldingsSummaryPayload(BaseModel):
    """Root payload for holdings summary outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_timestamp: str
    run_short_id: int | None = None
    run_id: str
    run_short_id_display: str
    symbol: str
    filings_processed: int
    positions: list[HoldingPosition] = Field(default_factory=list)
    summary: OwnershipSummary
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class HoldingsDiffPayload(BaseModel):
    """Root payload for holdings diff outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_timestamp: str
    run_short_id: int | None = None
    run_id: str
    run_short_id_display: str
    symbol: str
    diffs: list[HoldingsDiff] = Field(default_factory=list)


def write_holdings_summary_json(path, payload: HoldingsSummaryPayload) -> None:
    """Write holdings summary payload to JSON."""
    write_json(path, payload, exclude_none=True)


def write_holdings_summary_yaml(path, payload: HoldingsSummaryPayload) -> None:
    """Write holdings summary payload to YAML."""
    write_yaml(path, payload, exclude_none=True, sort_keys=False)


def write_holdings_diff_json(path, payload: HoldingsDiffPayload) -> None:
    """Write holdings diff payload to JSON."""
    write_json(path, payload, exclude_none=True)


def write_holdings_diff_yaml(path, payload: HoldingsDiffPayload) -> None:
    """Write holdings diff payload to YAML."""
    write_yaml(path, payload, exclude_none=True, sort_keys=False)
