# src/sec_nlp/pipelines/presets/warranty/config.py
"""Config model for the warranty pipeline."""

from pathlib import Path
from typing import ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings


class WarrantyConfig(BasePipelineSettings):
    """Configuration for SEC warranty data pipeline (XBRL-only, no LLM)."""

    model_config = SettingsConfigDict(
        env_prefix="SEC_NLP_WARRANTY_",
    )

    pipeline_type: ClassVar[Literal["warranty"]] = "warranty"

    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Filing type (only 10-K/annual supported for warranty data)",
    )

    limit: int | None = Field(
        default=1,
        ge=1,
        description="Maximum number of filings to process per symbol",
    )

    chunk_size: int = Field(
        default=15,
        ge=1,
        description="Max sentences per chunk (sentence-based splitting)",
    )
    chunk_overlap: int = Field(
        default=2,
        ge=0,
        description="Sentences to overlap between chunks",
    )

    xbrl_only: bool = Field(
        default=True,
        description="XBRL-only extraction mode (always True, LLM disabled)",
        json_schema_extra={"cli_args": {"nargs": "?", "const": True}},
    )

    keywords: list[str] = Field(
        default_factory=lambda: ["warranty", "accrual", "reserve", "revenue"],
        description="Keywords to bias loader toward warranty-relevant chunks (empty = no filtering)",
    )

    max_parallel_symbols: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Maximum symbols to process in parallel (1 = sequential)",
    )
    loader_use_async: bool = Field(
        default=True,
        description="Use async HTML processing in the loader",
    )
    loader_max_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Max workers for loader async processing",
    )

    export_format: Literal["json", "csv", "both"] = Field(
        default="both",
        description="Output format for warranty results (both = JSON+CSV)",
    )

    combined_csv: Path | None = Field(
        default=None,
        description=(
            "Optional path to a combined CSV (defaults to per-symbol pipeline output directory)"
        ),
    )

    use_item_8_filter: bool = Field(
        default=True,
        description="Apply Item 8 section filtering by default to focus on financial statements",
    )
    item_filter_numbers: list[str] = Field(
        default_factory=lambda: ["8"],
        description="Item numbers to include when section filtering (defaults to Item 8)",
    )
    item_filter_search_window: int = Field(
        default=3000,
        ge=500,
        description="Number of characters to scan when detecting Item sections",
    )
    item_filter_exclude_indices: bool = Field(
        default=True,
        description="Filter out index/table-of-contents pages when applying Item filters",
    )

    def pipeline_label(self) -> str:
        return "Warranty"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: FilingMode) -> FilingMode:
        """Validate that only annual filings are used."""
        if v != FilingMode.annual:
            raise ValueError(
                "WarrantyPipeline only supports annual filings (10-K). "
                f"Got: {v}"
            )
        return v
