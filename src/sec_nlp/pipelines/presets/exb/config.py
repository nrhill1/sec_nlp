# src/sec_nlp/pipelines/presets/exb/config.py
"""Config model for the Exhibit pipeline."""

from collections.abc import Sequence
from typing import ClassVar, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.vector.config import VectorConfig
from sec_nlp.types import JsonValue

from .steps.extract.contract_types import (
    ContractCategory,
    get_keywords_for_categories,
)
from .steps.search.search_config import SearchConfig

_EXHIBIT_CATEGORY_NUMBERS = {
    "contracts": ["10"],
    "subsidiaries": ["21"],
    "consents": ["23"],
    "financials": ["99"],
    "xbrl": ["101"],
}


class ExhibitConfig(BasePipelineSettings):
    """Configuration for SEC exhibit extraction pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="SEC_NLP_EXB_",
    )

    pipeline_type: ClassVar[Literal["exhibit"]] = "exhibit"

    symbols: list[str] = Field(
        default_factory=lambda: ["CAT", "DE", "HON", "PCAR", "CMI", "DHR"],
        description="Ticker symbols to process",
    )

    vdb: VectorConfig = Field(
        default_factory=lambda: VectorConfig(
            collection_name="exhibit",
            embedding_model="mxbai-embed-large",
            search_type="cosine",
            vector_size=1024,
        ),
        description="Vector database configuration for semantic search",
    )

    index_results: bool = Field(
        default=False,
        description="Explicitly embed and index extracted exhibits.",
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
        description="Filing type (10-K annual, 10-Q quarterly, or 8-K/6-K current)",
    )
    exhibit_categories: list[JsonValue] = Field(
        default_factory=lambda: [
            "contracts",
            "subsidiaries",
            "consents",
            "financials",
            "xbrl",
        ],
        description=(
            "Exhibit categories to include: contracts, subsidiaries, consents, "
            "financials, xbrl, all"
        ),
        json_schema_extra={
            "cli_args": {"nargs": "+", "action": "extend"},
        },
    )
    exhibit_numbers: list[JsonValue] = Field(
        default_factory=list,
        description=(
            "Optional exhibit numbers to include (e.g., 10, 21, 23, 99, 101). "
            "When empty, derived from exhibit_categories."
        ),
        json_schema_extra={
            "cli_args": {"nargs": "+", "action": "extend"},
        },
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

    # Contract type filtering (applies to contract exhibits only)
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
        description="Max sentences per chunk (sentence-based splitting)",
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
        description="Character window to scan when prefiltering HTML for contract signals",
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
        description=(
            "Keywords to search for in contract exhibits (used for scoring/ordering chunks)"
        ),
    )
    candidate_first: bool = Field(
        default=False,
        description=(
            "Use retrieve/EFTS candidate search to narrow accessions before exhibit parsing."
        ),
    )
    candidate_fallback_full_scan: bool = Field(
        default=True,
        description=(
            "When candidate-first finds no accessions, fall back to full exhibit scan."
        ),
    )
    candidate_queries: list[str] = Field(
        default_factory=list,
        description=(
            "Optional candidate queries for accession narrowing. "
            "Defaults to search_terms + category keywords when empty."
        ),
        json_schema_extra={
            "cli_args": {"nargs": "+", "action": "extend"},
        },
    )
    candidate_query_cap: int = Field(
        default=16,
        ge=1,
        le=100,
        description="Maximum number of candidate queries used per symbol.",
    )
    efts_candidates: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Maximum EFTS candidates fetched per candidate query.",
    )
    candidate_top_k: int = Field(
        default=120,
        ge=1,
        le=200,
        description="Maximum ranked candidate hits kept per symbol.",
    )
    candidate_query_term_min_hits: int = Field(
        default=1,
        ge=0,
        le=20,
        description=(
            "Minimum query-term overlap required in EFTS snippets for candidate retention."
        ),
    )
    candidate_query_term_min_ratio: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum query-term overlap ratio required in EFTS snippets for candidate retention."
        ),
    )
    candidate_stopword_aware_lexical: bool = Field(
        default=True,
        description="Enable stopword-aware lexical pruning for candidate ranking.",
    )

    def pipeline_label(self) -> str:
        return "Exhibit"

    @field_validator("search_terms", mode="before")
    @classmethod
    def normalize_search_terms(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            v = [part for part in v.replace(",", " ").split() if part]
        return [term.strip() for term in v]

    @field_validator("candidate_queries", mode="before")
    @classmethod
    def normalize_candidate_queries(
        cls, v: list[str] | str | None
    ) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            values = [v]
        else:
            values = list(v)

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            for part in str(raw).split("||"):
                cleaned = part.strip()
                if not cleaned:
                    continue
                key = cleaned.casefold()
                if key in seen:
                    continue
                seen.add(key)
                normalized.append(cleaned)
        return normalized

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
                "ExhibitPipeline supports annual (10-K), quarterly (10-Q), or current (8-K/6-K) filings. "
                f"Got: {v}"
            )
        return v

    @field_validator("exhibit_categories", mode="before")
    @classmethod
    def normalize_exhibit_categories(cls, v: JsonValue) -> list[JsonValue]:
        """Normalize exhibit categories input."""
        if isinstance(v, str):
            values = [part.strip() for part in v.replace(",", " ").split()]
        elif isinstance(v, Sequence) and not isinstance(v, str):
            values = list(v)
        else:
            values = []

        cleaned = []
        for item in values:
            if item is None or isinstance(item, bool):
                continue
            label = str(item).strip().lower()
            if not label:
                continue
            cleaned.append(label)

        if "all" in cleaned:
            return list(_EXHIBIT_CATEGORY_NUMBERS.keys())
        return cleaned

    @field_validator("contract_categories", mode="before")
    @classmethod
    def normalize_contract_categories(cls, v: list[str] | str) -> list[str]:
        """Normalize contract categories input."""
        if isinstance(v, str):
            v = [part.strip() for part in v.replace(",", " ").split() if part]
        return [cat.lower().strip() for cat in v]

    @field_validator("exhibit_numbers", mode="before")
    @classmethod
    def normalize_exhibit_numbers(cls, v: JsonValue) -> list[JsonValue]:
        """Normalize exhibit number inputs into a stable list."""
        if isinstance(v, (str, int, float)):
            values = [v]
        elif isinstance(v, Sequence) and not isinstance(v, str):
            values = list(v)
        else:
            values = []

        normalized: list[JsonValue] = []
        seen = set()
        for item in values:
            if item is None or isinstance(item, bool):
                continue
            cleaned = str(item).strip().lower()
            if not cleaned:
                continue
            cleaned = cleaned.replace("_", ".").replace("-", ".")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

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

    def get_exhibit_numbers(self) -> list[JsonValue]:
        """Return normalized exhibit numbers, falling back to categories."""
        numbers = self.normalize_exhibit_numbers(self.exhibit_numbers)
        if numbers:
            return numbers
        categories = self.normalize_exhibit_categories(self.exhibit_categories)
        derived: list[JsonValue] = []
        for category in categories:
            if not isinstance(category, str):
                continue
            bases = _EXHIBIT_CATEGORY_NUMBERS.get(category, [])
            derived.extend(bases)
        if derived:
            return derived
        default_numbers: list[JsonValue] = ["10"]
        return default_numbers

    def get_exhibit_categories(self) -> list[JsonValue]:
        """Return normalized categories, falling back to exhibit numbers."""
        numbers = self.normalize_exhibit_numbers(self.exhibit_numbers)
        if numbers:
            derived: list[JsonValue] = []
            for item in numbers:
                if not isinstance(item, str):
                    continue
                base = item.split(".")[0].strip()
                for category, bases in _EXHIBIT_CATEGORY_NUMBERS.items():
                    if base in bases and category not in derived:
                        derived.append(category)
            return derived

        categories = self.normalize_exhibit_categories(self.exhibit_categories)
        if categories:
            return categories

        numbers = self.get_exhibit_numbers()
        derived = []
        for item in numbers:
            if not isinstance(item, str):
                continue
            base = item.split(".")[0].strip()
            for category, bases in _EXHIBIT_CATEGORY_NUMBERS.items():
                if base in bases and category not in derived:
                    derived.append(category)
        return derived

    def classify_exhibit_number(self, value: JsonValue) -> JsonValue:
        """Map an exhibit number to a category when possible."""
        if isinstance(value, str):
            base = value.split(".")[0].strip().lower()
            if base:
                for category, bases in _EXHIBIT_CATEGORY_NUMBERS.items():
                    if base in bases:
                        return category
        return None

    def has_contract_exhibits(self) -> bool:
        """Return True if contract exhibits are in scope."""
        numbers = self.get_exhibit_numbers()
        for value in numbers:
            if isinstance(value, str) and value.split(".")[0].strip() == "10":
                return True
        categories = self.get_exhibit_categories()
        return "contracts" in categories

    def has_non_contract_exhibits(self) -> bool:
        """Return True if any non-contract exhibit categories are in scope."""
        numbers = self.get_exhibit_numbers()
        for value in numbers:
            if isinstance(value, str) and value.split(".")[0].strip() != "10":
                return True
        categories = self.get_exhibit_categories()
        return any(
            category for category in categories if category != "contracts"
        )
