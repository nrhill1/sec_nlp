from datetime import date
from pathlib import Path
from typing import Any

from _typeshed import Incomplete
from pydantic import BaseModel
from sec_edgar_downloader import Downloader

from sec_nlp.core.config import get_logger as get_logger
from sec_nlp.core.enums import FilingMode as FilingMode

logger: Incomplete

class SECFilingDownloader(BaseModel):
    email: str
    downloads_folder: Path
    company_name: str
    _symbols: set[str]
    _downloader: Downloader | None
    @classmethod
    def _ensure_folder(cls, v: Path) -> Path: ...
    def model_post_init(self, /, __ctx: Any) -> None: ...
    def add_symbol(self, symbol: str) -> None: ...
    def add_symbols(self, symbols: list[str]) -> None: ...
    def download_filings(
        self, mode: FilingMode = ..., start_date: date | None = None, end_date: date | None = None
    ) -> dict[str, bool]: ...
    def __repr__(self) -> str: ...
    def __str__(self) -> str: ...
