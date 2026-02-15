from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..config import HoldingsSettings as HoldingsSettings

@dataclass(frozen=True)
class DownloadedHoldingsFiling:
    symbol: str
    form_type: str
    accession_number: str
    filing_dir: Path
    filed_date: date | None

def download_holdings_filings(
    *, symbol: str, settings: HoldingsSettings
) -> list[DownloadedHoldingsFiling]: ...
