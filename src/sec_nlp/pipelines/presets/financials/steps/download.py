# src/sec_nlp/pipelines/presets/financials/steps/download.py
"""Download helpers for the financials pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.filings import get_filing_date_from_dir

from ..config import FinancialsSettings


@dataclass(frozen=True)
class DownloadedFiling:
    """Downloaded filing metadata used by downstream extraction steps."""

    symbol: str
    form_type: str
    accession_number: str
    filing_dir: Path
    filed_date: date | None


def _collect_form_dirs(
    *,
    symbol: str,
    form_type: str,
    base_dir: Path,
) -> list[DownloadedFiling]:
    form_dir = base_dir / "sec-edgar-filings" / symbol.upper() / form_type
    if not form_dir.exists():
        return []

    filings: list[DownloadedFiling] = []
    for accession_dir in form_dir.iterdir():
        if not accession_dir.is_dir():
            continue
        filings.append(
            DownloadedFiling(
                symbol=symbol.upper(),
                form_type=form_type,
                accession_number=accession_dir.name,
                filing_dir=accession_dir,
                filed_date=get_filing_date_from_dir(accession_dir),
            )
        )
    return filings


def _sort_key(filing: DownloadedFiling) -> tuple[date, float]:
    filed_date = filing.filed_date or date.min
    try:
        mtime = filing.filing_dir.stat().st_mtime
    except OSError:
        mtime = 0.0
    return filed_date, mtime


def download_financial_filings(
    *, symbol: str, settings: FinancialsSettings
) -> list[DownloadedFiling]:
    """Download and collect filing directories for a symbol."""
    from sec_edgar_downloader import Downloader

    normalized_symbol = symbol.strip().upper()
    start_date, end_date = settings.date_range
    downloader = Downloader(
        "SEC NLP Tool", settings.email, str(settings.dl_path)
    )

    for form_type in settings.form_types:
        try:
            downloader.get(
                form_type,
                normalized_symbol,
                after=start_date,
                before=end_date,
                limit=settings.periods,
                download_details=True,
            )
        except Exception as exc:
            logger.warning(
                "Download failed for %s (%s): %s",
                normalized_symbol,
                form_type,
                exc,
            )

    all_filings: list[DownloadedFiling] = []
    for form_type in settings.form_types:
        all_filings.extend(
            _collect_form_dirs(
                symbol=normalized_symbol,
                form_type=form_type,
                base_dir=settings.dl_path,
            )
        )

    deduped: list[DownloadedFiling] = []
    seen_accessions: set[str] = set()
    for filing in sorted(all_filings, key=_sort_key, reverse=True):
        if filing.accession_number in seen_accessions:
            continue
        seen_accessions.add(filing.accession_number)
        deduped.append(filing)
        if len(deduped) >= settings.periods:
            break

    return deduped
