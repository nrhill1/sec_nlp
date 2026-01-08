# src/sec_nlp/pipelines/presets/exb_10/config.py
"""Config model for the Exhibit 10 pipeline."""

from typing import ClassVar, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BaseConfig
from sec_nlp.pipelines.vector.config import VectorConfig

from .steps.extract.contract_types import (
    ContractCategory,
    get_keywords_for_categories,
)
from .steps.search.search_config import SearchConfig


class Exhibit10Config(BaseConfig):
    """Configuration for SEC Exhibit 10 extraction pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="EXB10_",
    )

    pipeline_type: ClassVar[Literal["exhibit10"]] = "exhibit10"

    symbols: list[str] = Field(
        default_factory=lambda: ["CAT", "DE", "HON", "PCAR", "CMI", "DHR"],
        description="OEM/manufacturer ticker symbols to process",
    )

    vdb: VectorConfig = Field(
        default_factory=lambda: VectorConfig(
            collection_name="exhibit_10",
            embedding_model="mxbai-embed-large",
            search_type="cosine",
            vector_size=1024,
        ),
        description="Vector database configuration for future semantic search",
    )

    dry_run: bool = Field(
        default=False,
        description="If True, run the pipeline without vector upload",
    )

    search: SearchConfig = Field(
        default_factory=SearchConfig,
        description="Semantic search configuration",
    )

    search_only: bool = Field(
        default=False,
        description="Skip chunking/indexing and only run semantic search on existing data",
        json_schema_extra={"cli_args": {"nargs": "?", "const": True}},
    )

    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Filing type (10-K annual, 10-Q quarterly, or 8-K current for Exhibit 10 material contracts)",
    )

    limit: int | None = Field(
        default=5,
        ge=1,
        description="Maximum number of filings to process per symbol",
    )

    batch_size: int = Field(
        default=16,
        ge=1,
        le=128,
        description="Number of chunks to process in parallel",
    )

    # Contract type filtering
    contract_categories: list[str] = Field(
        default_factory=lambda: ["supply"],
        description="Contract categories to analyze: supply, credit, employment, lease, license, service, all",
        json_schema_extra={"cli_args": {"nargs": "+", "action": "extend"}},
    )
    # Output format options
    export_format: Literal["json", "yaml", "csv", "both"] = Field(
        default="yaml",
        description="Output format: json, yaml, csv, or both (yaml+csv)",
        json_schema_extra={
            "cli_args": {"choices": ["json", "yaml", "csv", "both"]}
        },
    )
    verbose_output: bool = Field(
        default=False,
        description="Include detailed per-chunk analysis in output",
        json_schema_extra={"cli_args": {"nargs": "?", "const": True}},
    )

    chunk_size: int = Field(
        default=20,
        ge=1,
        description="Max sentences per chunk (sentence-based splitting for contracts)",
    )
    chunk_overlap: int = Field(
        default=3,
        ge=0,
        description="Sentences to overlap between chunks",
    )
    min_chunk_chars: int = Field(
        default=120,
        ge=0,
        description="Minimum characters a chunk must contain to be analyzed",
    )
    max_non_keyword_chunks: int | None = Field(
        default=25,
        description="Fallback non-keyword chunks to keep per filing (None = keep all; set to 0 to drop)",
    )
    max_chunks_per_filing: int | None = Field(
        default=None,
        ge=1,
        le=2000,
        description="Optional cap on analyzed chunks per filing after filtering",
    )
    require_keyword_categories: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Minimum distinct keyword categories that must appear to keep an exhibit pre-chunk",
    )
    adaptive_chunking: bool = Field(
        default=True,
        description="Enable adaptive chunk sizing based on exhibit length",
    )
    prefilter_allow_no_keyword: int = Field(
        default=3,
        ge=0,
        description="Number of exhibits/html files allowed through even without keyword hits (fallback to avoid empty runs)",
    )
    prefilter_keywords: bool = Field(
        default=True,
        description="If False, skip keyword prefiltering of entire exhibits/HTML before chunking",
    )
    prefilter_section_terms: bool = Field(
        default=True,
        description="If False, skip the section-term prefilter so all exhibits/HTML are processed",
    )
    chunk_prefilter_window: int = Field(
        default=6000,
        ge=500,
        description="Character window to scan when prefiltering HTML for Exhibit 10 signals",
    )
    chunk_prefilter_min_length: int = Field(
        default=40,
        ge=0,
        description="Minimum HTML length to process when prefiltering",
    )
    dedupe_chunks: bool = Field(
        default=True,
        description="Drop duplicate chunk bodies before indexing",
    )

    search_terms: list[str] = Field(
        default_factory=lambda: [
            "exclusive",
            "exclusivity",
            "exclusive supplier",
            "supply agreement",
            "component",
            "parts",
            "diesel engine",
            "aftermarket",
            "repair",
            "replacement",
            "maintenance",
            "service",
            "at cost",
            "cost plus",
            "near cost",
            "parts pricing",
            "aftermarket services",
        ],
        description="Keywords to search for in Exhibit 10 contracts (also used for scoring/ordering chunks)",
    )

    def pipeline_label(self) -> str:
        return "Exhibit 10"

    @field_validator("search_terms", mode="before")
    @classmethod
    def normalize_search_terms(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            v = [part for part in v.replace(",", " ").split() if part]
        return [term.strip() for term in v]

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: FilingMode) -> FilingMode:
        """Validate that only supported filing types are used."""
        if v not in (
            FilingMode.annual,
            FilingMode.quarterly,
            FilingMode.current,
        ):
            raise ValueError(
                "Exhibit10Pipeline supports annual (10-K), quarterly (10-Q), or current (8-K) filings. "
                f"Got: {v}"
            )
        return v

    @field_validator("contract_categories", mode="before")
    @classmethod
    def normalize_contract_categories(cls, v: list[str] | str) -> list[str]:
        """Normalize contract categories input."""
        if isinstance(v, str):
            v = [part.strip() for part in v.replace(",", " ").split() if part]
        return [cat.lower().strip() for cat in v]

    @model_validator(mode="after")
    def expand_contract_categories(self) -> Self:
        """Expand 'all' and add non-material categories if requested."""
        categories = list(self.contract_categories)

        if "all" in categories:
            categories = [cat.value for cat in ContractCategory]

        if categories != self.contract_categories:
            return self.model_copy(update={"contract_categories": categories})
        return self

    def get_active_categories(self) -> list[ContractCategory]:
        """Get list of ContractCategory filing_mode for active categories."""
        return [
            ContractCategory(cat)
            for cat in self.contract_categories
            if cat in [c.value for c in ContractCategory]
        ]

    def get_category_keywords(self) -> list[str]:
        """Get combined keywords for all active contract categories."""
        active = self.get_active_categories()
        return get_keywords_for_categories(active)
