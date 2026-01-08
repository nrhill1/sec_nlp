from pathlib import Path
from typing import ClassVar, Literal

from _typeshed import Incomplete

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.pipelines.base.config import BaseConfig as BaseConfig

class WarrantyConfig(BaseConfig):
    model_config: Incomplete
    pipeline_type: ClassVar[Literal["warranty"]]
    mode: FilingMode
    limit: int | None
    chunk_size: int
    chunk_overlap: int
    xbrl_only: bool
    keywords: list[str]
    max_parallel_symbols: int
    loader_use_async: bool
    loader_max_workers: int
    export_format: Literal["json", "csv", "both"]
    combined_csv: Path | None
    use_item_8_filter: bool
    item_filter_numbers: list[str]
    item_filter_search_window: int
    item_filter_exclude_indices: bool
    def pipeline_label(self) -> str: ...
    @classmethod
    def validate_mode(cls, v: FilingMode) -> FilingMode: ...
