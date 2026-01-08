from collections.abc import Iterable
from datetime import date
from pathlib import Path

from langchain_core.documents import Document

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.core.infra.logger import logger as logger

def filing_dir(base: Path, symbol: str, mode: FilingMode) -> Path: ...
def get_filing_date_from_dir(filing_dir_path: Path) -> date | None: ...
def html_paths_for_symbol(
    *,
    symbol: str,
    mode: FilingMode,
    base: Path,
    limit: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Path]: ...
def get_cik_for_ticker(
    *, ticker: str, company_name: str, email: str
) -> str: ...
def load_xbrl_facts(
    *,
    symbols: Iterable[str],
    tags: list[str],
    mode: FilingMode,
    downloads_folder: Path,
    limit_per_symbol: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Document]: ...
