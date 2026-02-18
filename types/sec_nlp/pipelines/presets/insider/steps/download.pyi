from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..config import InsiderSettings as InsiderSettings

DEFAULT_INSIDER_FORMS: tuple[str, ...]

@dataclass(frozen=True)
class DownloadedInsiderFiling:
    symbol: str
    form_type: str
    accession_number: str
    filing_dir: Path
    filed_date: date | None

def download_insider_filings(
    *, symbol: str, settings: InsiderSettings
) -> list[DownloadedInsiderFiling]: ...
