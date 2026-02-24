# src/sec_nlp/pipelines/presets/insider/steps/download.py
"""Download helpers for insider ownership filings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.filings import get_filing_date_from_dir

from ..config import InsiderSettings

DEFAULT_INSIDER_FORMS: tuple[str, ...] = ("3", "4", "5")


@dataclass(frozen=True)
class DownloadedInsiderFiling:
    """Downloaded filing metadata for insider parsing."""

    symbol: str
    form_type: str
    accession_number: str
    filing_dir: Path
    filed_date: date | None


def _effective_date_range(settings: InsiderSettings) -> tuple[date, date]:
    end_date = settings.end_date or date.today()
    start_date = settings.start_date or (
        end_date - timedelta(days=30 * settings.lookback_months)
    )
    return start_date, end_date


def _effective_forms(settings: InsiderSettings) -> tuple[str, ...]:
    if settings.forms:
        cleaned = [item.strip().upper() for item in settings.forms if item]
        if cleaned:
            return tuple(dict.fromkeys(cleaned))
    return DEFAULT_INSIDER_FORMS


def _collect_form_dirs(
    *,
    symbol: str,
    form_type: str,
    base_dir: Path,
    start_date: date,
    end_date: date,
) -> list[DownloadedInsiderFiling]:
    form_dir = base_dir / "sec-edgar-filings" / symbol.upper() / form_type
    if not form_dir.exists():
        return []

    filings: list[DownloadedInsiderFiling] = []
    for accession_dir in form_dir.iterdir():
        if not accession_dir.is_dir():
            continue

        filed_date = get_filing_date_from_dir(accession_dir)
        if filed_date and (filed_date < start_date or filed_date > end_date):
            continue

        filings.append(
            DownloadedInsiderFiling(
                symbol=symbol.upper(),
                form_type=form_type,
                accession_number=accession_dir.name,
                filing_dir=accession_dir,
                filed_date=filed_date,
            )
        )

    return filings


def _sort_key(filing: DownloadedInsiderFiling) -> tuple[date, float]:
    filed_date = filing.filed_date or date.min
    try:
        mtime = filing.filing_dir.stat().st_mtime
    except OSError:
        mtime = 0.0
    return filed_date, mtime


def download_insider_filings(
    *, symbol: str, settings: InsiderSettings
) -> list[DownloadedInsiderFiling]:
    """Download and collect Form 3/4/5 directories for a symbol."""
    from sec_edgar_downloader import Downloader

    normalized_symbol = symbol.strip().upper()
    start_date, end_date = _effective_date_range(settings)
    form_types = _effective_forms(settings)

    downloader = Downloader(
        "SEC NLP Tool", settings.email, str(settings.dl_path)
    )

    for form_type in form_types:
        try:
            downloader.get(
                form_type,
                normalized_symbol,
                after=start_date,
                before=end_date,
                limit=None,
                download_details=True,
            )
        except Exception as exc:
            logger.warning(
                "Download failed for %s (%s): %s",
                normalized_symbol,
                form_type,
                exc,
            )

    all_filings: list[DownloadedInsiderFiling] = []
    for form_type in form_types:
        all_filings.extend(
            _collect_form_dirs(
                symbol=normalized_symbol,
                form_type=form_type,
                base_dir=settings.dl_path,
                start_date=start_date,
                end_date=end_date,
            )
        )

    deduped: list[DownloadedInsiderFiling] = []
    seen_accessions: set[str] = set()
    for filing in sorted(all_filings, key=_sort_key, reverse=True):
        if filing.accession_number in seen_accessions:
            continue
        seen_accessions.add(filing.accession_number)
        deduped.append(filing)

    return deduped
