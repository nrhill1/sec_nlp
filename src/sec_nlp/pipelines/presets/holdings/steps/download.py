"""Download helpers for 13F holdings filings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.filings import get_filing_date_from_dir

from ..config import HoldingsSettings


@dataclass(frozen=True)
class DownloadedHoldingsFiling:
    """Downloaded filing metadata for holdings parsing."""

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
) -> list[DownloadedHoldingsFiling]:
    form_dir = base_dir / "sec-edgar-filings" / symbol.upper() / form_type
    if not form_dir.exists():
        return []

    filings: list[DownloadedHoldingsFiling] = []
    for accession_dir in form_dir.iterdir():
        if not accession_dir.is_dir():
            continue
        filings.append(
            DownloadedHoldingsFiling(
                symbol=symbol.upper(),
                form_type=form_type,
                accession_number=accession_dir.name,
                filing_dir=accession_dir,
                filed_date=get_filing_date_from_dir(accession_dir),
            )
        )

    return filings


def _sort_key(filing: DownloadedHoldingsFiling) -> tuple[date, float]:
    filed_date = filing.filed_date or date.min
    try:
        mtime = filing.filing_dir.stat().st_mtime
    except OSError:
        mtime = 0.0
    return filed_date, mtime


def _build_form_requests(forms: list[str]) -> dict[str, bool]:
    """Map configured forms into downloader-compatible requests.

    sec-edgar-downloader expects base forms (e.g. ``13F-HR``) plus
    ``include_amends=True`` to include amended variants (e.g. ``13F-HR/A``).
    """
    requests: dict[str, bool] = {}
    for form in forms:
        cleaned = form.strip().upper()
        if cleaned.endswith("/A"):
            base_form = cleaned.removesuffix("/A")
            requests[base_form] = True
            continue
        requests[cleaned] = requests.get(cleaned, False)
    return requests


def download_holdings_filings(
    *, symbol: str, settings: HoldingsSettings
) -> list[DownloadedHoldingsFiling]:
    """Download and collect 13F filing directories for a symbol."""
    from sec_edgar_downloader import Downloader

    normalized_symbol = symbol.strip().upper()
    start_date, end_date = settings.date_range

    downloader = Downloader(
        "SEC NLP Tool", settings.email, str(settings.dl_path)
    )

    configured_forms = settings.forms or ["13F-HR", "13F-HR/A"]
    form_requests = _build_form_requests(configured_forms)
    for form_type, include_amends in form_requests.items():
        try:
            downloader.get(
                form_type,
                normalized_symbol,
                after=start_date,
                before=end_date,
                limit=settings.quarters,
                include_amends=include_amends,
                download_details=True,
            )
        except Exception as exc:
            logger.warning(
                "Download failed for %s (%s, include_amends=%s): %s",
                normalized_symbol,
                form_type,
                include_amends,
                exc,
            )

    all_filings: list[DownloadedHoldingsFiling] = []
    form_dirs = set(form_requests)
    for form_type, include_amends in form_requests.items():
        if include_amends:
            # Some cached datasets may store amended directories explicitly.
            form_dirs.add(f"{form_type}/A")
    for form_type in sorted(form_dirs):
        all_filings.extend(
            _collect_form_dirs(
                symbol=normalized_symbol,
                form_type=form_type,
                base_dir=settings.dl_path,
            )
        )

    deduped: list[DownloadedHoldingsFiling] = []
    seen_accessions: set[str] = set()
    for filing in sorted(all_filings, key=_sort_key, reverse=True):
        if filing.accession_number in seen_accessions:
            continue
        seen_accessions.add(filing.accession_number)
        deduped.append(filing)
        if len(deduped) >= settings.quarters:
            break

    return deduped
