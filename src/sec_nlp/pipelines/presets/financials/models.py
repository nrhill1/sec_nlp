# src/sec_nlp/pipelines/presets/financials/models.py
"""Data models for financial statement extraction."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.types import JsonValue


class FinancialFact(BaseModel):
    """Normalized fact extracted from XBRL."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    accession_number: str
    form_type: str
    concept: str
    raw_tag: str
    value: float
    unit: str | None = None
    decimals: int | None = None
    period_start: str | None = None
    period_end: str | None = None
    period_instant: str | None = None
    segment: str | None = None
    source_file: str | None = None


class FinancialStatement(BaseModel):
    """Per-period normalized financial statement row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: str
    accession_number: str | None = None

    revenue: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    stockholders_equity: float | None = None
    cash_and_cash_equivalents: float | None = None
    long_term_debt: float | None = None
    operating_income: float | None = None
    gross_profit: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None

    current_ratio: float | None = None
    debt_to_equity: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    roe: float | None = None


class FinancialsResult(BasePipelineResult):
    """Result model for financial statement extraction pipeline."""

    pipeline_type: ClassVar[Literal["financials"]] = "financials"

    model_config = ConfigDict(frozen=True, extra="ignore")

    symbols_processed: int = Field(
        default=0,
        description="Number of symbols processed by the pipeline.",
    )
    periods_generated: int = Field(
        default=0,
        description="Total number of financial periods emitted.",
    )

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["symbols_processed"] = self.symbols_processed
        fields["periods_generated"] = self.periods_generated
        return fields
