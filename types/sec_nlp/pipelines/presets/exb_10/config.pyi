from typing import ClassVar, Literal, Self

from _typeshed import Incomplete

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.pipelines.base.config import BaseConfig as BaseConfig
from sec_nlp.pipelines.vector.config import VectorConfig as VectorConfig

from .steps.extract.contract_types import (
    ContractCategory as ContractCategory,
    get_keywords_for_categories as get_keywords_for_categories,
)
from .steps.search.search_config import SearchConfig as SearchConfig

class Exhibit10Config(BaseConfig):
    model_config: Incomplete
    pipeline_type: ClassVar[Literal["exhibit10"]]
    symbols: list[str]
    vdb: VectorConfig
    dry_run: bool
    search: SearchConfig
    search_only: bool
    mode: FilingMode
    limit: int | None
    batch_size: int
    contract_categories: list[str]
    export_format: Literal["json", "yaml", "csv", "both"]
    verbose_output: bool
    chunk_size: int
    chunk_overlap: int
    min_chunk_chars: int
    max_non_keyword_chunks: int | None
    max_chunks_per_filing: int | None
    require_keyword_categories: int
    adaptive_chunking: bool
    prefilter_allow_no_keyword: int
    prefilter_keywords: bool
    prefilter_section_terms: bool
    chunk_prefilter_window: int
    chunk_prefilter_min_length: int
    dedupe_chunks: bool
    search_terms: list[str]
    def pipeline_label(self) -> str: ...
    @classmethod
    def normalize_search_terms(cls, v: list[str] | str) -> list[str]: ...
    @classmethod
    def validate_mode(cls, v: FilingMode) -> FilingMode: ...
    @classmethod
    def normalize_contract_categories(cls, v: list[str] | str) -> list[str]: ...
    def expand_contract_categories(self) -> Self: ...
    def get_active_categories(self) -> list[ContractCategory]: ...
    def get_category_keywords(self) -> list[str]: ...
