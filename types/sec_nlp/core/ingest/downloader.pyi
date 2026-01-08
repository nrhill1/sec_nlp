from collections.abc import Iterable
from datetime import date
from pathlib import Path

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.core.ingest import filings as filings
from sec_nlp.core.ingest.types import (
    DownloadResult as DownloadResult,
    DownloadResults as DownloadResults,
)

def download_filings(
    *,
    symbols: Iterable[str],
    mode: FilingMode,
    work_folder: Path,
    company_name: str,
    email: str,
    after_date: date | None = None,
    before_date: date | None = None,
    limit_per_symbol: int | None = None,
) -> DownloadResults: ...
