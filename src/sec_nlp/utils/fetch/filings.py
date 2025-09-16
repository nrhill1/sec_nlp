# utils/fetch/filings.py
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, List, Dict

from tqdm import tqdm
from sec_edgar_downloader import Downloader  # type: ignore

logger = logging.getLogger(__name__)


class SECFilingDownloader:
    """
    Downloads SEC filings (e.g., 10-K or 10-Q) for provided ticker symbols.

    Args:
        email (str): Contact email for SEC requests.
        downloads_folder (Path): Base path for saving downloaded filings.
        company_name (str): Optional name for SEC identification.
    """

    SUPPORTED_MODES = {
        "annual": "10-K",
        "quarterly": "10-Q",
    }

    def __init__(
        self,
        email: str,
        downloads_folder: Path,
        company_name: str = "My Company Inc.",
    ):
        self._email: str = email.strip()
        self._downloads_folder: Path = downloads_folder
        self._company_name: str = company_name.strip()
        self._symbols: Set[str] = set()

        self._downloads_folder.mkdir(parents=True, exist_ok=True)

        self._downloader = Downloader(
            self._company_name,
            self._email,
            str(self._downloads_folder)
        )

    def add_symbol(self, symbol: str):
        clean = symbol.strip().upper()
        self._symbols.add(clean)

    def add_symbols(self, symbols: List[str]):
        for symbol in symbols:
            self.add_symbol(symbol)

    def _validate_date(self, date_str: Optional[str], name: str):
        if date_str:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"{name} must be in YYYY-MM-DD format")

    def download_filings(
        self,
        mode: str = "annual",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Download filings for all added symbols within optional date range.

        Args:
            mode (str): 'annual' for 10-K or 'quarterly' for 10-Q.
            start_date (Optional[str]): Lower bound in YYYY-MM-DD format.
            end_date (Optional[str]): Upper bound in YYYY-MM-DD format.

        Returns:
            Dict[str, bool]: Per-symbol success status.
        """
        if mode not in self.SUPPORTED_MODES:
            raise ValueError(
                f"Unsupported mode: {mode}. Must be one of: {list(self.SUPPORTED_MODES)}")

        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")

        if not self._symbols:
            raise ValueError("No symbols added for download")

        filing_type = self.SUPPORTED_MODES[mode]

        results: Dict[str, bool] = {}

        logger.info(
            f"Beggining {filing_type} downloads for {list(self._symbols)}")

        for symbol in tqdm(sorted(self._symbols),
                           desc=f"Downloading {filing_type} files..."):
            try:
                self._downloader.get(
                    filing_type,
                    symbol,
                    after=start_date,
                    before=end_date,
                    download_details=True
                )
                results[symbol] = True
            except Exception as e:
                results[symbol] = False

        return results

    def __repr__(self) -> str:
        symbols = ",".join(sorted(self._symbols)) or "<none>"
        return (
            f"<SECFilingDownloader company_name={self._company_name} "
            f"symbols=[{symbols}] downloads_folder={self._downloads_folder!r}>"
        )

    def __str__(self) -> str:
        return f"SECFilingDownloader tracking {len(self._symbols)} symbol(s)"
