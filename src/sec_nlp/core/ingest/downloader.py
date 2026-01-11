"""Download helpers for SEC filings."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from sec_edgar_downloader import Downloader

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest import filings
from sec_nlp.core.ingest.types import DownloadResult, DownloadResults


def _success_download_result(
    *, downloaded: int, form_type: str, skipped_existing: int | None = None
) -> DownloadResult:
    result: DownloadResult = {
        "success": True,
        "downloaded": downloaded,
        "form_type": form_type,
    }
    if skipped_existing is not None:
        result["skipped_existing"] = skipped_existing
    return result


def _error_download_result(error: str) -> DownloadResult:
    return {
        "success": False,
        "error": error,
        "downloaded": 0,
    }


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
) -> DownloadResults:
    """Download filings for symbols into work_folder."""
    download_results: DownloadResults = {}
    downloader = Downloader(company_name, email, str(work_folder))
    filing_type = mode.form

    for symbol in sorted(symbols):
        symbol_dir = filings.filing_dir(work_folder, symbol, mode)
        existing_accessions: list[str] = []
        if symbol_dir.exists():
            existing_accessions = [
                p.name for p in symbol_dir.iterdir() if p.is_dir()
            ]
            existing_count = len(existing_accessions)
            if (
                limit_per_symbol is not None
                and existing_count >= limit_per_symbol
            ):
                logger.info(
                    "Skipping download for %s %s; already have %d accessions (limit=%d)",
                    symbol,
                    filing_type,
                    existing_count,
                    limit_per_symbol,
                )
                download_results[symbol] = _success_download_result(
                    downloaded=0,
                    form_type=filing_type,
                    skipped_existing=existing_count,
                )
                continue
            if existing_count:
                logger.info(
                    "Found %d existing accessions for %s %s; downloading up to %s more",
                    existing_count,
                    symbol,
                    filing_type,
                    "unlimited"
                    if limit_per_symbol is None
                    else max(limit_per_symbol - existing_count, 0),
                )

        try:
            download_limit = (
                None
                if limit_per_symbol is None
                else max(limit_per_symbol - len(existing_accessions), 0)
            )
            if download_limit == 0:
                download_results[symbol] = _success_download_result(
                    downloaded=0,
                    form_type=filing_type,
                    skipped_existing=len(existing_accessions),
                )
                continue
            n = downloader.get(
                filing_type,
                symbol,
                after=after_date,
                before=before_date,
                limit=download_limit,
                download_details=True,
            )
            download_results[symbol] = _success_download_result(
                downloaded=n or 0,
                form_type=filing_type,
            )
        except Exception as exc:
            logger.error("Download failed for %s: %s", symbol, exc)
            download_results[symbol] = _error_download_result(str(exc))

    return download_results


def _download_single_symbol(
    *,
    symbol: str,
    mode: FilingMode,
    work_folder: Path,
    company_name: str,
    email: str,
    after_date: date | None = None,
    before_date: date | None = None,
    limit_per_symbol: int | None = None,
) -> tuple[str, DownloadResult]:
    """Download filings for a single symbol (sync).

    Returns:
        Tuple of (symbol, download_result)
    """
    downloader = Downloader(company_name, email, str(work_folder))
    filing_type = mode.form
    symbol_dir = filings.filing_dir(work_folder, symbol, mode)
    existing_accessions: list[str] = []

    if symbol_dir.exists():
        existing_accessions = [
            p.name for p in symbol_dir.iterdir() if p.is_dir()
        ]
        existing_count = len(existing_accessions)
        if limit_per_symbol is not None and existing_count >= limit_per_symbol:
            logger.info(
                "Skipping download for %s %s; already have %d accessions (limit=%d)",
                symbol,
                filing_type,
                existing_count,
                limit_per_symbol,
            )
            return (
                symbol,
                _success_download_result(
                    downloaded=0,
                    form_type=filing_type,
                    skipped_existing=existing_count,
                ),
            )

    try:
        download_limit = (
            None
            if limit_per_symbol is None
            else max(limit_per_symbol - len(existing_accessions), 0)
        )
        if download_limit == 0:
            return (
                symbol,
                _success_download_result(
                    downloaded=0,
                    form_type=filing_type,
                    skipped_existing=len(existing_accessions),
                ),
            )
        n = downloader.get(
            filing_type,
            symbol,
            after=after_date,
            before=before_date,
            limit=download_limit,
            download_details=True,
        )
        return (
            symbol,
            _success_download_result(downloaded=n or 0, form_type=filing_type),
        )
    except Exception as exc:
        logger.error("Download failed for %s: %s", symbol, exc)
        return (symbol, _error_download_result(str(exc)))


async def download_filings_async(
    *,
    symbols: Iterable[str],
    mode: FilingMode,
    work_folder: Path,
    company_name: str,
    email: str,
    after_date: date | None = None,
    before_date: date | None = None,
    limit_per_symbol: int | None = None,
    max_concurrent: int = 3,
) -> DownloadResults:
    """Download filings asynchronously for multiple symbols.

    Uses asyncio.to_thread() to run downloads concurrently without blocking.
    SEC EDGAR has rate limits, so we limit concurrency.

    Args:
        symbols: Ticker symbols to download
        mode: Filing mode (annual/quarterly)
        work_folder: Download destination
        company_name: Company name for SEC user agent
        email: Contact email for SEC user agent
        after_date: Optional start date filter
        before_date: Optional end date filter
        limit_per_symbol: Max filings per symbol
        max_concurrent: Max concurrent downloads (default 3 to respect rate limits)

    Returns:
        Download results by symbol
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    sorted_symbols = sorted(symbols)

    async def download_with_semaphore(
        symbol: str,
    ) -> tuple[str, DownloadResult]:
        async with semaphore:
            return await asyncio.to_thread(
                _download_single_symbol,
                symbol=symbol,
                mode=mode,
                work_folder=work_folder,
                company_name=company_name,
                email=email,
                after_date=after_date,
                before_date=before_date,
                limit_per_symbol=limit_per_symbol,
            )

    results = await asyncio.gather(
        *[download_with_semaphore(s) for s in sorted_symbols]
    )

    return dict(results)
