"""Config model for the financials pipeline."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.pipelines.base.config import BasePipelineSettings


class FinancialsSettings(BasePipelineSettings):
    """Configuration for structured financial statement extraction."""

    model_config = SettingsConfigDict(env_prefix="SEC_NLP_FINANCIALS_")

    pipeline_type: ClassVar[Literal["financials"]] = "financials"

    form_types: list[str] = Field(
        default_factory=lambda: ["10-K", "10-Q"],
        description="SEC form types to fetch for financial statement extraction.",
    )
    periods: int = Field(
        default=8,
        ge=1,
        le=40,
        description="Maximum number of filings/periods to process per symbol.",
    )
    compute_ratios: bool = Field(
        default=True,
        description="Compute derived financial ratios from extracted line items.",
    )
    output_format: Literal["csv", "json", "yaml", "all"] = Field(
        default="csv",
        description="Output file format to emit.",
    )
    include_delta_report: bool = Field(
        default=False,
        description="Include period-over-period deltas in JSON/YAML outputs.",
    )

    @field_validator("form_types", mode="before")
    @classmethod
    def normalize_form_types(cls, value: list[str] | str | None) -> list[str]:
        """Normalize SEC form identifiers to uppercase/hyphen format."""
        if value is None:
            return ["10-K", "10-Q"]
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        for form_type in value:
            cleaned = form_type.strip().upper()
            if cleaned in ("10K", "10Q", "8K"):
                cleaned = f"{cleaned[:-1]}-{cleaned[-1]}"
            if cleaned:
                normalized.append(cleaned)

        return normalized or ["10-K", "10-Q"]

    def pipeline_label(self) -> str:
        return "Financials"
