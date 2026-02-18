from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..config import FinancialsSettings as FinancialsSettings

@dataclass(frozen=True)
class DownloadedFiling:
    symbol: str
    form_type: str
    accession_number: str
    filing_dir: Path
    filed_date: date | None

def download_financial_filings(
    *, symbol: str, settings: FinancialsSettings
) -> list[DownloadedFiling]: ...
