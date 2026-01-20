import abc
from abc import ABC, abstractmethod
from datetime import date, datetime
from functools import cached_property as cached_property
from pathlib import Path
from typing import ClassVar, Literal, Self

from _typeshed import Incomplete
from pydantic_settings import BaseSettings

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.utils import is_valid_email as is_valid_email
from sec_nlp.types import (
    InitSubclassKwargs as InitSubclassKwargs,
    JsonDict as JsonDict,
    JsonObject as JsonObject,
)

class BasePipelineSettings(BaseSettings, ABC, metaclass=abc.ABCMeta):
    pipeline_type: ClassVar[str]
    model_config: Incomplete
    email: str
    verbose: bool
    log_format: Literal["simple", "detailed", "json"]
    log_file: Path | None
    fresh: bool
    cleanup: bool
    dry_run: bool
    run_id: int
    dl_path: Path
    out_path: Path
    symbols: list[str]
    mode: FilingMode
    start_date: date | None
    end_date: date | None
    @classmethod
    def __pydantic_init_subclass__(
        cls, **kwargs: InitSubclassKwargs
    ) -> None: ...
    def model_post_init(self, /, __context: JsonObject | None) -> None: ...
    @abstractmethod
    def pipeline_label(self) -> str: ...
    @classmethod
    def parse_start_date(cls, v: str | date | None) -> date | None: ...
    @classmethod
    def parse_end_date(cls, v: str | date | None) -> date | None: ...
    @classmethod
    def normalize_symbols(cls, v: list[str] | str) -> list[str]: ...
    @classmethod
    def coerce_run_id(cls, v: int | str | None) -> int: ...
    @classmethod
    def validate_log_file(cls, v: Path | None) -> Path | None: ...
    @classmethod
    def validate_email(cls, v: str) -> str: ...
    def validate_date_range(self) -> Self: ...
    @cached_property
    def date_range(self) -> tuple[date, date]: ...
    def setup_paths(self) -> None: ...
    def get_symbol_output_dir(self, symbol: str) -> Path: ...
    def summary(self) -> str: ...
    def print_summary(self) -> None: ...
    @property
    def short_id(self) -> int: ...
    @property
    def short_id_display(self) -> str: ...
    @property
    def run_timestamp(self) -> datetime: ...
    def complete_run(
        self, success: bool = True, metadata: str | JsonDict | None = None
    ) -> None: ...
    @property
    def num_symbols(self) -> int: ...
    @property
    def date_range_days(self) -> int: ...
    def get_date_range(self) -> tuple[date, date]: ...
    def get_log_level(self) -> str: ...
