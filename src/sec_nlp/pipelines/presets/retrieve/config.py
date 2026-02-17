"""Config model for retrieve pipeline."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings


class RetrieveSettings(BasePipelineSettings):
    """Configuration for EFTS-first retrieval pipeline."""

    model_config = SettingsConfigDict(env_prefix="SEC_NLP_RETRIEVE_")

    pipeline_type: ClassVar[Literal["retrieve"]] = "retrieve"

    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Default filing mode when forms are not explicitly set.",
    )
    forms: list[str] | None = Field(
        default_factory=lambda: ["10-K", "10-Q"],
        description="SEC forms to include in retrieval candidate search.",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="User retrieval queries to execute.",
        json_schema_extra={
            "cli_args": {
                "nargs": "+",
                "action": "extend",
                "aliases": ["--q", "--query", "--queries"],
            }
        },
    )
    sections: list[str] = Field(
        default_factory=list,
        description="Optional section IDs to target (stored for future chunk filtering).",
    )
    top_k: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum ranked hits to return per symbol.",
    )
    efts_candidates: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Maximum EFTS candidates fetched per query.",
    )
    output_format: Literal["csv", "json", "yaml", "all"] = Field(
        default="json",
        description="Output file format to emit.",
    )

    @field_validator("queries", mode="before")
    @classmethod
    def normalize_queries(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part.strip() for part in value.split("||") if part.strip()]

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            cleaned = raw.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)
        return normalized

    @field_validator("sections", mode="before")
    @classmethod
    def normalize_sections(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            cleaned = raw.strip().upper()
            if not cleaned:
                continue
            if cleaned.startswith("ITEM"):
                cleaned = cleaned.removeprefix("ITEM").strip()
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)
        return normalized

    def pipeline_label(self) -> str:
        return "Retrieve"
