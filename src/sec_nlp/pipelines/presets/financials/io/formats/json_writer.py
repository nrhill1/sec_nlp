"""JSON/YAML payload writer for financials outputs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.output_io import write_json, write_yaml
from sec_nlp.types import JsonValue

from ...models import FinancialStatement
from ...steps.aggregate import FinancialDelta


class FinancialsOutputPayload(BaseModel):
    """Root payload for financial statement outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    filings_processed: int
    periods: list[FinancialStatement] = Field(default_factory=list)
    delta_report: dict[str, FinancialDelta] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


def write_financials_json(path, payload: FinancialsOutputPayload) -> None:
    """Write financials payload to JSON."""
    write_json(path, payload, exclude_none=True)


def write_financials_yaml(path, payload: FinancialsOutputPayload) -> None:
    """Write financials payload to YAML."""
    write_yaml(path, payload, exclude_none=True, sort_keys=False)
