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
from sec_nlp.pipelines.base.config import BaseConfig
from sec_nlp.pipelines.llm.config import LLMConfig
from sec_nlp.pipelines.metadata.filters import MetadataFilters
from sec_nlp.pipelines.vector.config import VectorConfig
from sec_nlp.prompts import ANALYZE_PROMPT_PATH


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

    # Filing Parameters
    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Filing type to process (10-K, 10-Q, or 8-K)",
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
