# sec_nlp/utils/downloader.py
from datetime import date
from pathlib import Path

from pydantic import BaseModel, PrivateAttr, field_validator
from sec_edgar_downloader import Downloader  # type: ignore
from tqdm import tqdm

from sec_nlp.core.config import get_logger
from sec_nlp.core.enums import FilingMode

logger = get_logger(__name__)


class SECFilingDownloader(BaseModel):
    """
    Downloads SEC filings for provided ticker symbols.
    """

    email: str
    downloads_folder: Path
    company_name: str = "My Company Inc."

    _symbols: set[str] = PrivateAttr(default_factory=set)
    _downloader: Downloader | None = PrivateAttr(default=None)

    @field_validator("downloads_folder")
    @classmethod
    def _ensure_folder(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    def model_post_init(self, __ctx) -> None:
        self._downloader = Downloader(self.company_name, self.email, str(self.downloads_folder))

    def add_symbol(self, symbol: str) -> None:
        self._symbols.add(symbol.strip().upper())

    def add_symbols(self, symbols: list[str]) -> None:
        for s in symbols:
            self.add_symbol(s)

    def download_filings(
        self,
        mode: FilingMode = FilingMode.annual,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, bool]:
        """
        Download filings for all added symbols within optional date range.

        Args:
            mode: FilingMode.annual.form -> "10-K", FilingMode.quarterly.form -> "10-Q"
        """

        if not self._symbols:
            raise ValueError("No symbols added for download")

        filing_type = mode.form  # "10-K" or "10-Q"
        results: dict[str, bool] = {}

        logger.info(
            "Beginning %s downloads for %d symbol(s) in mode %s",
            filing_type,
            len(self._symbols),
            mode.value,
        )

        for symbol in tqdm(sorted(self._symbols), desc=f"Downloading {filing_type} files..."):
            try:
                self._downloader.get(  # type: ignore[union-attr]
                    filing_type,
                    symbol,
                    after=start_date,
                    before=end_date,
                    download_details=True,
                )
                results[symbol] = True
            except Exception:
                results[symbol] = False

        return results

    def __repr__(self) -> str:
        symbols = ",".join(sorted(self._symbols)) or "<none>"
        return f"<SECFilingDownloader company_name={self.company_name} symbols=[{symbols}] downloads_folder={self.downloads_folder!r}>"

    def __str__(self) -> str:
        return f"SECFilingDownloader tracking {len(self._symbols)} symbol(s)"
