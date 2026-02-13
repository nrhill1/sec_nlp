"""Config model for insider pipeline."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings


class InsiderSettings(BasePipelineSettings):
    """Configuration for insider trading analysis."""

    model_config = SettingsConfigDict(env_prefix="SEC_NLP_INSIDER_")

    pipeline_type: ClassVar[Literal["insider"]] = "insider"

    mode: FilingMode = Field(
        default=FilingMode.insider,
        description="Filing type mode for insider ownership forms.",
    )
    forms: list[str] | None = Field(
        default_factory=lambda: ["3", "4", "5"],
        description="SEC ownership forms to include for insider analysis.",
    )
    lookback_months: int = Field(
        default=12,
        ge=1,
        le=60,
        description="Lookback horizon for insider filings when explicit dates are omitted.",
    )
    alert_cluster_threshold: int = Field(
        default=3,
        ge=2,
        le=20,
        description="Minimum unique insiders trading in a short window to trigger cluster alerts.",
    )
    alert_window_days: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Window size in days used for cluster and market-move checks.",
    )
    large_trade_threshold_shares: float = Field(
        default=100_000.0,
        ge=1.0,
        description="Threshold for large single trade alerts based on transaction share count.",
    )
    output_format: Literal["csv", "json", "yaml", "all"] = Field(
        default="csv",
        description="Output format for insider pipeline artifacts.",
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: FilingMode) -> FilingMode:
        if value != FilingMode.insider:
            raise ValueError(
                "Insider pipeline only supports insider filing mode (Forms 3/4/5)."
            )
        return value

    @field_validator("forms", mode="before")
    @classmethod
    def validate_forms(cls, value: list[str] | str | None) -> list[str] | None:
        if value is None:
            return ["3", "4", "5"]
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        for form in value:
            cleaned = form.strip().upper().replace("FORM", "")
            if cleaned not in {"3", "4", "5"}:
                raise ValueError(
                    "Insider pipeline only supports forms 3, 4, and 5."
                )
            normalized.append(cleaned)
        return normalized or ["3", "4", "5"]

    @field_validator("lookback_months", mode="before")
    @classmethod
    def parse_lookback_months(cls, value: int | str) -> int:
        if isinstance(value, int):
            return value
        cleaned = value.strip().lower()
        if cleaned.endswith("months"):
            cleaned = cleaned.removesuffix("months").strip()
        if cleaned.endswith("month"):
            cleaned = cleaned.removesuffix("month").strip()
        if cleaned.endswith("mos"):
            cleaned = cleaned.removesuffix("mos").strip()
        if cleaned.endswith("mo"):
            cleaned = cleaned.removesuffix("mo").strip()
        if cleaned.endswith("m"):
            cleaned = cleaned.removesuffix("m").strip()
        return int(cleaned)

    def pipeline_label(self) -> str:
        return "Insider"
