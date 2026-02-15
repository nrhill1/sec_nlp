"""Config model for holdings pipeline."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings


class HoldingsSettings(BasePipelineSettings):
    """Configuration for 13F holdings analysis."""

    model_config = SettingsConfigDict(env_prefix="SEC_NLP_HOLDINGS_")

    pipeline_type: ClassVar[Literal["holdings"]] = "holdings"

    mode: FilingMode = Field(
        default=FilingMode.holdings,
        description="Filing mode for holdings analysis.",
    )
    forms: list[str] | None = Field(
        default_factory=lambda: ["13F-HR", "13F-HR/A"],
        description="13F form types to include.",
    )
    quarters: int = Field(
        default=4,
        ge=1,
        le=24,
        description="Maximum quarters of filings to process per symbol.",
    )
    top_holders: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of largest holdings to include in summary output.",
    )
    cusip: str | None = Field(
        default=None,
        description="Optional CUSIP filter for output rows and summary metrics.",
    )
    filer_ciks: list[str] = Field(
        default_factory=list,
        description="Optional filer CIK filter for future by-filer workflows.",
    )
    output_format: Literal["csv", "json", "yaml", "all"] = Field(
        default="csv",
        description="Output file format to emit.",
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: FilingMode) -> FilingMode:
        if value != FilingMode.holdings:
            raise ValueError(
                "Holdings pipeline only supports holdings filing mode (13F-HR)."
            )
        return value

    @field_validator("forms", mode="before")
    @classmethod
    def validate_forms(cls, value: list[str] | str | None) -> list[str] | None:
        if value is None:
            return ["13F-HR", "13F-HR/A"]
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        for form in value:
            cleaned = form.strip().upper()
            if cleaned not in {"13F-HR", "13F-HR/A"}:
                raise ValueError(
                    "Holdings pipeline only supports forms 13F-HR and 13F-HR/A."
                )
            normalized.append(cleaned)
        return normalized or ["13F-HR", "13F-HR/A"]

    @field_validator("cusip", mode="before")
    @classmethod
    def normalize_cusip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        return cleaned or None

    def pipeline_label(self) -> str:
        return "Holdings"
