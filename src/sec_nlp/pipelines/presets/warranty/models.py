# src/sec_nlp/pipelines/presets/warranty/models.py
"""Data models for warranty pipeline."""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.types import JsonValue


class WarrantyResult(BasePipelineResult):
    """Result model for warranty data extraction."""

    model_config = ConfigDict(
        extra="forbid",
    )

    pipeline_type: ClassVar[Literal["warranty"]] = "warranty"

    warranty_liability: float | None = Field(
        default=None,
        description="Total warranty liabilities/accruals in millions USD",
    )
    warranty_payout: float | None = Field(
        default=None,
        description="Warranty payments/settlements in millions USD",
    )
    net_revenue: float | None = Field(
        default=None,
        description="Net revenue from equipment/product sales in millions USD",
    )
    period: str | None = Field(
        default=None,
        description="Fiscal year or period for the data (e.g., '2024', 'FY2023')",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score for the extraction (0.0-1.0)",
    )

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["confidence"] = self.confidence
        return fields


class WarrantyInput(BaseModel):
    """Input schema for warranty data extraction chain."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    chunk: str
    symbol: str
