from typing import ClassVar, Literal

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.core.text.filters import (
    SectionPattern as SectionPattern,
    SectionType as SectionType,
)
from sec_nlp.pipelines.base.config import BaseConfig as BaseConfig
from sec_nlp.pipelines.llm.config import LLMConfig as LLMConfig
from sec_nlp.pipelines.metadata.filters import (
    MetadataFilters as MetadataFilters,
)
from sec_nlp.pipelines.vector.config import VectorConfig as VectorConfig
from sec_nlp.prompts import ANALYZE_PROMPT_PATH as ANALYZE_PROMPT_PATH

class SearchConfig(BaseModel):
    model_config: Incomplete
    queries: list[str]
    limit: int
    score_threshold: float
    query_term_min_hits: int
    query_term_min_ratio: float
    query_term_min_len: int
    analyze: bool
    analyze_limit: int
    export_results: bool
    metadata_filters: MetadataFilters

class AnalyzeConfig(BaseConfig):
    model_config: Incomplete
    pipeline_type: ClassVar[Literal["analyze"]]
    preset: (
        Literal["quick", "laptop", "thorough", "comprehensive", "rare_earths"]
        | None
    )
    symbols: list[str]
    llm: LLMConfig
    vdb: VectorConfig
    vector_mode: Literal["off", "read", "write"]
    search: SearchConfig
    mode: FilingMode
    loader_use_async: bool
    loader_max_workers: int
    limit: int | None
    section_type: SectionType | None
    section_numbers: list[str]
    custom_section_pattern: str | None
    filter_indices: bool
    search_window: int
    chunk_size: int
    chunk_overlap: int
    chunking_mode: Literal["sentence", "semantic"]
    semantic_similarity_threshold: float
    semantic_min_chunk_sentences: int
    semantic_max_chunk_sentences: int
    keywords: list[str]
    topics: list[str]
    min_topic_hits: int
    max_chunk_length: int | None
    prioritize_topics: bool
    top_k_chunks: int | None
    adaptive_top_k_cap: int | None
    enable_tracing: bool
    trace_log_prompts: bool
    keyword_mode: Literal["any", "all"]
    batch_size: int
    confidence_threshold: float
    confidence_mode: Literal["llm", "calibrated"]
    llm_retry_attempts: int
    llm_retry_backoff: float
    analysis_fields: list[str]
    max_chunks_per_filing: int | None
    skip_empty_sections: bool
    min_chunk_length: int
    skip_categories: list[str]
    deduplicate_chunks: bool
    similarity_threshold_dedup: float
    simhash_bits: int
    simhash_max_distance: int
    export_format: Literal["json", "csv", "yaml", "both", "yaml_csv"]
    include_raw_chunks: bool
    aggregate_by_filing: bool
    validate_config: bool
    collect_metrics: bool
    def pipeline_label(self) -> str: ...
    def get_search_queries(self) -> list[str]: ...
    def get_section_pattern(self) -> SectionPattern | None: ...
