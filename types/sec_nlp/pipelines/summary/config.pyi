from datetime import date
from pathlib import Path
from typing import Any, Self

from _typeshed import Incomplete

from sec_nlp.core.enums import FilingMode as FilingMode
from sec_nlp.pipelines.base import BaseConfig as BaseConfig
from sec_nlp.pipelines.settings import LLMSettings as LLMSettings
from sec_nlp.pipelines.settings import VectorDBSettings as VectorDBSettings

class SummaryConfig(BaseConfig):
    model_config: Incomplete
    pipeline_type: str
    llm: LLMSettings
    vdb: VectorDBSettings
    email: str
    dl_path: Path
    out_path: Path
    symbols: list[str]
    mode: FilingMode
    start_date: date | None
    end_date: date | None
    keyword: str
    limit: int | None
    batch_size: int
    max_retries: int
    fresh: bool
    cleanup: bool
    @classmethod
    def normalize_symbols(cls, v: list[str] | str) -> list[str]: ...
    @classmethod
    def validate_keyword(cls, v: str) -> str: ...
    @classmethod
    def validate_email(cls, v: str) -> str: ...
    @classmethod
    def parse_date(cls, v: str | date | None) -> date | None: ...
    def validate_date_range(self) -> Self: ...
    def ensure_paths_exist(self) -> Self: ...
    def get_date_range(self) -> tuple[date, date]: ...
    def get_prompt_path(self) -> Path: ...
    def to_pipeline_kwargs(self) -> dict[str, Any]: ...
