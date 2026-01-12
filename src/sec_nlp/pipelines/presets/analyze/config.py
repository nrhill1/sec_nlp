# src/sec_nlp/pipelines/presets/analyze/config.py
"""Configuration for generalized document analysis pipeline."""

from typing import ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.text.filters import SectionPattern, SectionType
from sec_nlp.core.text.section_patterns import (
    HOLDINGS_SECTION_PATTERNS,
    PROXY_SECTION_PATTERNS,
    REGISTRATION_SECTION_PATTERNS,
)
from sec_nlp.pipelines.base.config import BaseConfig
from sec_nlp.pipelines.llm.config import LLMConfig
from sec_nlp.pipelines.metadata.filters import MetadataFilters
from sec_nlp.pipelines.vector.config import VectorConfig
from sec_nlp.prompts import (
    ANALYZE_PROMPT_PATH,
    HOLDINGS_PROMPT_PATH,
    PROXY_PROMPT_PATH,
)
from sec_nlp.types import JsonDict, JsonValue

from .market import MarketConfig, MarketGranularity


class EFTSConfig(BaseModel):
    """Configuration for SEC EDGAR Full-Text Search (EFTS) integration."""

    model_config = ConfigDict(
        defer_build=True,
        frozen=True,
        extra="ignore",
    )

    enabled: bool = Field(
        default=False,
        description="Enable EFTS search to discover filings beyond local downloads",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum EFTS results to fetch per query",
    )
    score_threshold: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum EFTS relevance score to include (0 = no threshold)",
    )
    auto_download: bool = Field(
        default=True,
        description="Automatically download high-scoring EFTS hits not yet local",
    )
    auto_download_limit: int = Field(
        default=5,
        ge=0,
        le=20,
        description="Maximum filings to auto-download from EFTS results (0 = disabled)",
    )
    forms: list[str] = Field(
        default_factory=list,
        description="Form types to include in EFTS search (empty = use pipeline mode)",
    )
    expand_date_range: bool = Field(
        default=True,
        description="Expand EFTS date range beyond pipeline config for broader discovery",
    )
    date_range_years: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Years of filings to search when expand_date_range is enabled",
    )


class SearchConfig(BaseModel):
    """Configuration for semantic search functionality."""

    model_config = ConfigDict(
        defer_build=True,
        frozen=True,
        extra="ignore",
    )

    queries: list[str] = Field(
        default_factory=list,
        description="Search queries to run (search is enabled when non-empty)",
        json_schema_extra={
            "cli_args": {
                "nargs": "+",
                "action": "extend",
                "aliases": ["--queries"],
            }
        },
    )
    limit: int = Field(
        default=10,
        ge=1,
        description="Maximum results per query",
    )
    score_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "Similarity threshold: for cosine/euclid (distance) lower is better "
            "so this acts as a max distance; for dot-product higher is better"
        ),
    )
    query_term_min_hits: int = Field(
        default=1,
        ge=0,
        description=(
            "Minimum number of query terms that must appear in a chunk to keep a hit "
            "(0 disables lexical gating)"
        ),
    )
    query_term_min_ratio: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum fraction of query terms that must appear in a chunk "
            "(0 disables ratio gating)"
        ),
    )
    query_term_min_len: int = Field(
        default=3,
        ge=1,
        description="Minimum length for query terms used in lexical gating",
    )
    analyze: bool = Field(
        default=True,
        description="Run LLM analysis on search results",
    )
    analyze_limit: int = Field(
        default=10,
        ge=1,
        description="Maximum number of search hits to analyze per query",
    )
    export_results: bool = Field(
        default=True,
        description="Export search results to files",
    )
    metadata_filters: MetadataFilters = Field(
        default_factory=dict,
        description="Exact-match metadata filters applied to vector searches",
    )


class AnalyzeConfig(BaseConfig):
    """Configuration for generalized document analysis pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="ANALYZE_",
    )

    pipeline_type: ClassVar[Literal["analyze"]] = "analyze"

    # Preset configuration (applied before other options)
    preset: (
        Literal[
            "quick",
            "laptop",
            "thorough",
            "comprehensive",
            "rare_earths",
        ]
        | None
    ) = Field(
        default=None,
        description=(
            "Use a preset configuration (quick, laptop, thorough, comprehensive, rare-earths)"
        ),
    )

    @field_validator("preset", mode="before")
    @classmethod
    def _normalize_preset(cls, v: str | None) -> str | None:
        """Convert kebab-case preset names to snake_case for CLI compatibility."""
        if v is None:
            return None
        return v.replace("-", "_")

    symbols: list[str] = Field(
        default_factory=list,
        description="Ticker symbols to process",
        json_schema_extra={"cli_args": {"aliases": ["-s"]}},
    )

    # LLM Configuration
    llm: LLMConfig = Field(
        default_factory=lambda: LLMConfig(
            prompt_file=ANALYZE_PROMPT_PATH,
            model_name="llama3.2:1b",
            temperature=0.25,  # Slightly higher for recall while keeping consistency
        ),
        description="LLM configuration for document analysis",
    )

    # Vector Database Configuration
    vdb: VectorConfig = Field(
        default_factory=lambda: VectorConfig(
            collection_name="analyze",
            embedding_model="bge-m3",
            search_type="mmr",
            vector_size=1024,
        ),
        description="Vector database configuration for semantic search",
    )

    # Run embedding
    vector_mode: Literal["off", "read", "write"] = Field(
        default="write",
        description=(
            "Vector DB mode: 'off' disables vector DB entirely; "
            "'read' initializes vector DB for search only; "
            "'write' initializes and stores relevant chunks"
        ),
        json_schema_extra={
            "cli_args": {
                "choices": ["off", "read", "write"],
                "aliases": ["-vm"],
            }
        },
    )

    # Search Configuration
    search: SearchConfig = Field(
        default_factory=SearchConfig,
        description="Post-analysis semantic search configuration",
    )

    # EFTS (EDGAR Full-Text Search) Configuration
    efts: EFTSConfig = Field(
        default_factory=EFTSConfig,
        description="SEC EDGAR Full-Text Search integration for filing discovery",
    )

    efts_enabled: bool | None = Field(
        default=None,
        description="Enable EFTS search via CLI flag (overrides efts.enabled).",
        json_schema_extra={
            "cli_args": {
                "aliases": ["--efts-enabled", "--efts"],
                "action": "store_true",
            }
        },
    )

    # Filing Parameters
    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Filing type to process (10-K, 10-Q, 8-K, DEF 14A, 13F-HR, S-1, S-3)",
    )
    loader_use_async: bool = Field(
        default=True,
        description="Use async HTML processing in the loader",
    )
    loader_max_workers: int = Field(
        default=2,
        ge=1,
        le=16,
        description="Max workers for loader async processing",
    )

    limit: int | None = Field(
        default=5,
        ge=1,
        description="Maximum number of filings to process per symbol",
    )

    market: MarketConfig = Field(
        default_factory=MarketConfig,
        description="Optional market enrichment configuration for the symbol range.",
    )

    market_enabled: bool | None = Field(
        default=None,
        description="Enable market enrichment via CLI flag (overrides market.enabled).",
        json_schema_extra={
            "cli_args": {
                "aliases": ["--market-enabled"],
                "action": "store_true",
            }
        },
    )
    market_ticker: str | None = Field(
        default=None,
        description="Ticker to use for market enrichment when enabled.",
        json_schema_extra={"cli_args": {"aliases": ["--market-ticker"]}},
    )
    market_granularity: MarketGranularity | None = Field(
        default=None,
        description="Granularity to request when market enrichment is enabled.",
        json_schema_extra={"cli_args": {"aliases": ["--market-granularity"]}},
    )
    market_limit: int | None = Field(
        default=None,
        ge=1,
        description="Limit of aggregated rows to include when market enrichment is enabled.",
        json_schema_extra={"cli_args": {"aliases": ["--market-limit"]}},
    )

    @model_validator(mode="before")
    @classmethod
    def _apply_market_flags(
        cls, values: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        market_values: dict[str, JsonValue] = {}
        raw_market = values.get("market")
        if isinstance(raw_market, MarketConfig):
            market_values.update(raw_market.model_dump())
        elif isinstance(raw_market, dict):
            market_values.update(raw_market)
        market_flags = {
            "enabled": values.get("market_enabled"),
            "ticker": values.get("market_ticker"),
            "granularity": values.get("market_granularity"),
            "limit": values.get("market_limit"),
        }
        for key, flag in market_flags.items():
            if flag is not None:
                market_values[key] = flag
        if market_values:
            values["market"] = market_values
        return values

    @model_validator(mode="before")
    @classmethod
    def _apply_efts_flags(
        cls, values: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        """Apply CLI flags to EFTS config."""
        efts_values: dict[str, JsonValue] = {}
        raw_efts = values.get("efts")
        if isinstance(raw_efts, EFTSConfig):
            efts_values.update(raw_efts.model_dump())
        elif isinstance(raw_efts, dict):
            efts_values.update(raw_efts)
        efts_enabled = values.get("efts_enabled")
        if efts_enabled is not None:
            efts_values["enabled"] = efts_enabled
        if efts_values:
            values["efts"] = efts_values
        return values

    @staticmethod
    def _combine_section_patterns(patterns: JsonDict) -> JsonValue:
        combined_parts = []
        for pattern in patterns.values():
            if isinstance(pattern, str) and pattern:
                combined_parts.append(f"({pattern})")
        if not combined_parts:
            return None
        return "|".join(combined_parts)

    @model_validator(mode="before")
    @classmethod
    def _apply_mode_defaults(cls, values: JsonDict) -> JsonDict:
        raw_mode = values.get("mode")
        if isinstance(raw_mode, FilingMode):
            mode = raw_mode
        elif isinstance(raw_mode, str):
            try:
                mode = FilingMode(raw_mode)
            except ValueError:
                return values
        else:
            return values

        section_type = values.get("section_type")
        section_numbers = values.get("section_numbers")
        custom_pattern = values.get("custom_section_pattern")
        should_apply_sections = (
            section_type is None
            and not section_numbers
            and custom_pattern is None
        )

        if should_apply_sections:
            if mode == FilingMode.proxy:
                combined = cls._combine_section_patterns(PROXY_SECTION_PATTERNS)
            elif mode == FilingMode.holdings:
                combined = cls._combine_section_patterns(
                    HOLDINGS_SECTION_PATTERNS
                )
            elif mode in (
                FilingMode.registration,
                FilingMode.shelf_registration,
            ):
                combined = cls._combine_section_patterns(
                    REGISTRATION_SECTION_PATTERNS
                )
            else:
                combined = None

            if combined is not None:
                values["section_type"] = SectionType.CUSTOM
                values["custom_section_pattern"] = combined

        prompt_path = None
        if mode == FilingMode.proxy:
            prompt_path = PROXY_PROMPT_PATH
        elif mode == FilingMode.holdings:
            prompt_path = HOLDINGS_PROMPT_PATH

        if prompt_path is not None:
            raw_llm = values.get("llm")
            if isinstance(raw_llm, LLMConfig):
                if raw_llm.prompt_file is None:
                    llm_values = raw_llm.model_dump()
                    llm_values["prompt_file"] = prompt_path
                    values["llm"] = llm_values
            elif isinstance(raw_llm, dict):
                if raw_llm.get("prompt_file") is None:
                    llm_values = dict(raw_llm)
                    llm_values["prompt_file"] = prompt_path
                    values["llm"] = llm_values
            elif raw_llm is None:
                values["llm"] = {"prompt_file": prompt_path}

        return values

    section_type: SectionType | None = Field(
        default=None,
        description="Type of section to filter: 'exhibit', 'item', 'part', or 'custom'",
    )

    section_numbers: list[str] = Field(
        default_factory=list,
        description="Specific section numbers to extract (e.g., ['10', '21'] for exhibits); ignored when use_section_filter=False",
        json_schema_extra={"cli_args": {"nargs": "+", "action": "extend"}},
    )

    @field_validator("section_numbers", mode="before")
    @classmethod
    def _coerce_section_numbers(cls, v: list[str | int] | None) -> list[str]:
        """Coerce numeric section numbers to strings for CLI compatibility."""
        if v is None:
            return []
        return [str(item) for item in v]

    custom_section_pattern: str | None = Field(
        default=None,
        description="Custom regex pattern for section matching (when section_type='custom')",
    )

    filter_indices: bool = Field(
        default=True,
        description="Filter out table of contents and index documents",
    )

    search_window: int = Field(
        default=3000,
        ge=100,
        description="Number of characters to search at document start for section markers",
    )

    # Content Filtering
    chunk_size: int = Field(
        default=50,
        ge=1,
        description="Sentences per chunk when splitting sections",
    )
    chunk_overlap: int = Field(
        default=2,
        ge=0,
        description="Sentence overlap between chunks when splitting sections",
    )
    chunking_mode: Literal["sentence", "semantic"] = Field(
        default="semantic",
        description=(
            "Chunking strategy: 'sentence' uses fixed sentence counts; "
            "'semantic' uses embeddings to detect topic boundaries"
        ),
        json_schema_extra={
            "cli_args": {
                "choices": ["sentence", "semantic"],
                "aliases": ["-cm"],
            }
        },
    )
    semantic_similarity_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Similarity threshold for semantic chunking; lower values create more splits"
        ),
    )
    semantic_min_chunk_sentences: int = Field(
        default=3,
        ge=1,
        description="Minimum sentences per chunk when using semantic chunking",
    )
    semantic_max_chunk_sentences: int = Field(
        default=50,
        ge=1,
        description="Maximum sentences per chunk when using semantic chunking",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords to prioritize in content (optional)",
        json_schema_extra={
            "cli_args": {"nargs": "+", "action": "extend", "aliases": ["-k"]}
        },
    )
    topics: list[str] = Field(
        default_factory=list,
        description="Topic keywords used to score and prioritize chunks",
        json_schema_extra={
            "cli_args": {"nargs": "+", "action": "extend", "aliases": ["-t"]}
        },
    )
    min_topic_hits: int = Field(
        default=1,
        ge=0,
        description="Minimum number of topic keyword hits required to keep a chunk",
    )
    max_chunk_length: int | None = Field(
        default=200000,
        ge=10,
        description="Optional maximum characters allowed per chunk (None disables)",
    )
    prioritize_topics: bool = Field(
        default=True,
        description="When true, order chunks by topic hit count before analysis",
    )
    top_k_chunks: int | None = Field(
        default=60,
        ge=1,
        description="Keep only the top-K scored chunks after preprocessing (None disables)",
    )
    adaptive_top_k_cap: int | None = Field(
        default=None,
        ge=1,
        description="Optional cap applied to top-k selection to prevent huge runs when many chunks remain",
    )

    # Tracing / logging
    enable_tracing: bool = Field(
        default=False,
        description="Enable LangChain callback-based tracing for LLM calls",
    )
    trace_log_prompts: bool = Field(
        default=False,
        description="Include prompt text in trace logs (may be verbose)",
    )

    keyword_mode: Literal["any", "all"] = Field(
        default="any",
        description="Whether content must match 'any' or 'all' keywords",
        json_schema_extra={
            "cli_args": {"choices": ["any", "all"], "aliases": ["-km"]}
        },
    )

    # Analysis Configuration
    batch_size: int = Field(
        default=8,
        ge=1,
        le=32,
        description="Number of chunks to process in parallel with LLM",
    )

    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score to consider results relevant",
    )
    confidence_mode: Literal["llm", "calibrated"] = Field(
        default="calibrated",
        description=(
            "How to set confidence_score: use raw LLM output or calibrate "
            "with query-term overlap and evidence signals"
        ),
    )
    llm_retry_attempts: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Retry attempts for batch LLM calls before falling back to per-item",
    )
    llm_retry_backoff: float = Field(
        default=1.0,
        ge=0.0,
        description="Initial backoff (seconds) for LLM retry; doubles each attempt",
    )

    analysis_fields: list[str] = Field(
        default_factory=lambda: [
            "is_relevant",
            "confidence_score",
            "summary",
            "key_points",
            "reasoning",
            "query_match_terms",
            "missing_query_terms",
            "binding_status",
            "contingencies",
            "impact_channels",
            "impact_direction",
            "impact_magnitude",
            "impact_horizon",
            "impact_confidence",
            "impact_rationale",
            "extracted_entities",
            "tags",
            "evidence_spans",
            "source_excerpt",
            "severity",
            "sentiment",
            "forward_looking",
            "follow_up_questions",
        ],
        description="Fields to extract from LLM analysis",
    )

    # Processing Options
    max_chunks_per_filing: int | None = Field(
        default=None,
        ge=1,
        description="Maximum chunks to analyze per filing (None = unlimited)",
    )

    skip_empty_sections: bool = Field(
        default=True,
        description="Skip sections with no substantial content",
    )

    min_chunk_length: int = Field(
        default=300,
        ge=10,
        description="Minimum characters required for a chunk to be analyzed",
    )
    skip_categories: list[str] = Field(
        default_factory=list,
        description="Document categories to skip entirely (case-insensitive, based on metadata.category). Empty = no category skip.",
        json_schema_extra={"cli_args": {"nargs": "+", "action": "extend"}},
    )

    deduplicate_chunks: bool = Field(
        default=True,
        description="Remove duplicate or highly similar chunks before analysis",
    )

    similarity_threshold_dedup: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "Token-overlap threshold for deduplication (lower is more aggressive; "
            "higher requires closer matches)"
        ),
    )
    simhash_bits: int = Field(
        default=64,
        ge=32,
        le=128,
        description="Number of bits for SimHash fingerprint (64 is standard)",
    )
    simhash_max_distance: int = Field(
        default=3,
        ge=0,
        le=32,
        description="Maximum hamming distance to consider documents as duplicates (lower = stricter)",
    )

    export_format: Literal["json", "csv", "yaml", "both", "yaml_csv"] = Field(
        default="yaml",
        description="Output format for analysis results (yaml_csv = YAML+CSV; both = JSON+CSV)",
        json_schema_extra={
            "cli_args": {"choices": ["json", "csv", "yaml", "both", "yaml_csv"]}
        },
    )

    include_raw_chunks: bool = Field(
        default=False,
        description="Include raw document chunks in output files",
    )

    show_timeline: bool = Field(
        default=False,
        description="Display related filing timelines in logs when available",
    )

    aggregate_by_filing: bool = Field(
        default=True,
        description="Aggregate results by filing (vs per-chunk output)",
    )

    # Validation Options
    validate_config: bool = Field(
        default=True,
        description="Run pre-flight validation before execution",
    )

    collect_metrics: bool = Field(
        default=True,
        description="Collect and report performance metrics",
    )

    def pipeline_label(self) -> str:
        return "Analyze"

    def get_search_queries(self) -> list[str]:
        """Return configured search queries, falling back to topics."""
        if self.search.queries:
            return list(self.search.queries)
        if self.topics:
            return list(self.topics)
        return []

    def get_section_pattern(self) -> SectionPattern | None:
        """Create SectionPattern from config.

        Returns:
            Configured SectionPattern for filtering
        """
        if not self.section_type:
            return None

        return SectionPattern(
            section_type=self.section_type,
            numbers=self.section_numbers,
            custom_pattern=self.custom_section_pattern,
            require_exact_match=False,
        )

    @model_validator(mode="after")
    def _validate_vector_and_search(self) -> Self:
        """Guardrails for vector/search combinations."""
        if self.get_search_queries() and self.vector_mode == "off":
            raise ValueError(
                "search queries (search.queries or topics) require vector_mode to be 'read' or 'write'"
            )
        return self
