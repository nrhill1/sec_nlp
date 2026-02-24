# src/sec_nlp/core/ingest/downloader.py
"""Download helpers for SEC filings."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path

from sec_edgar_downloader import Downloader

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.types import DownloadResult, DownloadResults
from sec_nlp.core.types import coerce_json_dict
from sec_nlp.types import JsonDict, JsonValue


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
    form_types = mode.forms
    form_label = ", ".join(form_types)

    for symbol in sorted(symbols):
        total_downloaded = 0
        total_skipped = 0
        errors = []

        for form_type in form_types:
            symbol_dir = (
                work_folder / "sec-edgar-filings" / symbol.upper() / form_type
            )
            existing_accessions = []
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
                        form_type,
                        existing_count,
                        limit_per_symbol,
                    )
                    total_skipped += existing_count
                    continue
                if existing_count:
                    logger.info(
                        "Found %d existing accessions for %s %s; downloading up to %s more",
                        existing_count,
                        symbol,
                        form_type,
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
                    total_skipped += len(existing_accessions)
                    continue
                n = downloader.get(
                    form_type,
                    symbol,
                    after=after_date,
                    before=before_date,
                    limit=download_limit,
                    download_details=True,
                )
                total_downloaded += n or 0
            except Exception as exc:
                logger.error(
                    "Download failed for %s %s: %s", symbol, form_type, exc
                )
                errors.append(f"{form_type}: {exc}")

        if errors:
            result = _error_download_result("; ".join(errors))
            result["downloaded"] = total_downloaded
            result["form_type"] = form_label
            if total_skipped:
                result["skipped_existing"] = total_skipped
            download_results[symbol] = result
        else:
            result = _success_download_result(
                downloaded=total_downloaded,
                form_type=form_label,
                skipped_existing=total_skipped if total_skipped else None,
            )
            download_results[symbol] = result

    return download_results


def download_accessions(
    *,
    symbol: str,
    accessions: Sequence[str],
    accession_cik_map: Mapping[str, str],
    mode: FilingMode,
    work_folder: Path,
    company_name: str,
    email: str,
) -> DownloadResults:
    """Download specific accession numbers into the standard filings folder."""
    results: DownloadResults = {}
    unique_accessions: list[str] = []
    seen: set[str] = set()
    for accession in accessions:
        cleaned = accession.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique_accessions.append(cleaned)

    if not unique_accessions:
        return results

    user_agent = f"{company_name} {email}"
    submissions_cache: dict[str, JsonDict] = {}
    supplemental_cache: dict[str, JsonDict] = {}

    for accession in unique_accessions:
        cik = accession_cik_map.get(accession)
        if not isinstance(cik, str) or not cik.strip():
            results[accession] = _error_download_result(
                "Missing CIK for accession"
            )
            continue

        try:
            primary_doc = _lookup_primary_document(
                accession=accession,
                cik=cik,
                user_agent=user_agent,
                submissions_cache=submissions_cache,
                supplemental_cache=supplemental_cache,
            )
        except Exception as exc:
            logger.warning(
                "Failed to resolve primary document for %s: %s",
                accession,
                exc,
            )
            results[accession] = _error_download_result(
                "Primary document lookup failed"
            )
            continue

        if primary_doc is None:
            results[accession] = _error_download_result(
                "Primary document not found"
            )
            continue

        try:
            form_type = None
            if mode == FilingMode.insider:
                payload = submissions_cache.get(cik)
                if payload is None:
                    payload = _fetch_submissions_payload(cik, user_agent)
                    submissions_cache[cik] = payload
                form_value = _find_form_type(payload, accession)
                if form_value is None:
                    for name in _iter_submission_files(payload):
                        extra_payload = supplemental_cache.get(name)
                        if extra_payload is None:
                            extra_payload = _fetch_submission_file(
                                name, user_agent
                            )
                            supplemental_cache[name] = extra_payload
                        form_value = _find_form_type(extra_payload, accession)
                        if form_value is not None:
                            break
                form_type = _normalize_form_type(form_value)
            if not isinstance(form_type, str) or not form_type:
                form_type = mode.form

            accession_dir = (
                work_folder
                / "sec-edgar-filings"
                / symbol.upper()
                / form_type
                / accession
            )
            downloaded, skipped = _download_accession_files(
                accession=accession,
                cik=cik,
                primary_doc=primary_doc,
                accession_dir=accession_dir,
                mode=mode,
                user_agent=user_agent,
            )
            results[accession] = _success_download_result(
                downloaded=downloaded,
                form_type=form_type,
                skipped_existing=skipped,
            )
        except Exception as exc:
            logger.warning(
                "Failed to download accession %s: %s", accession, exc
            )
            results[accession] = _error_download_result(str(exc))

    return results


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
    results = download_filings(
        symbols=[symbol],
        mode=mode,
        work_folder=work_folder,
        company_name=company_name,
        email=email,
        after_date=after_date,
        before_date=before_date,
        limit_per_symbol=limit_per_symbol,
    )
    result = results.get(symbol)
    if result is None:
        return (symbol, _error_download_result("Download result missing"))
    return (symbol, result)


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


def _lookup_primary_document(
    *,
    accession: str,
    cik: str,
    user_agent: str,
    submissions_cache: dict[str, JsonDict],
    supplemental_cache: dict[str, JsonDict],
) -> str | None:
    payload = submissions_cache.get(cik)
    if payload is None:
        payload = _fetch_submissions_payload(cik, user_agent)
        submissions_cache[cik] = payload

    primary_doc = _find_primary_document(payload, accession)
    if primary_doc is not None:
        return primary_doc

    for name in _iter_submission_files(payload):
        extra_payload = supplemental_cache.get(name)
        if extra_payload is None:
            extra_payload = _fetch_submission_file(name, user_agent)
            supplemental_cache[name] = extra_payload
        primary_doc = _find_primary_document(extra_payload, accession)
        if primary_doc is not None:
            return primary_doc

    return None


def _download_accession_files(
    *,
    accession: str,
    cik: str,
    primary_doc: str,
    accession_dir: Path,
    mode: FilingMode,
    user_agent: str,
) -> tuple[int, int]:
    accession_dir.mkdir(parents=True, exist_ok=True)

    skipped_existing = 0
    downloaded_accessions = 0

    acc_no_dash = accession.replace("-", "")
    cik_path = cik.lstrip("0")
    base_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{acc_no_dash}/"
    )

    raw_path = accession_dir / "full-submission.txt"
    if raw_path.exists():
        skipped_existing += 1
    else:
        raw_url = f"{base_url}{accession}.txt"
        _download_to_path(raw_url, raw_path, user_agent)

    primary_doc_path = primary_doc.replace("\\", "/").lstrip("/")
    primary_name = Path(primary_doc_path).name
    primary_suffix = Path(primary_name).suffix.lower()
    if primary_suffix == ".htm":
        primary_suffix = ".html"
    if not primary_suffix:
        primary_suffix = ".html"
    primary_path = accession_dir / f"primary-document{primary_suffix}"
    if primary_path.exists():
        skipped_existing += 1
    else:
        primary_url = f"{base_url}{primary_doc_path}"
        _download_to_path(primary_url, primary_path, user_agent)

    primary_ready = primary_path.exists()
    if primary_ready or mode == FilingMode.holdings:
        downloaded_accessions = 1

    return downloaded_accessions, skipped_existing


def _fetch_submissions_payload(cik: str, user_agent: str) -> JsonDict:
    cik_value = cik.strip().zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_value}.json"
    return _fetch_json(url, user_agent)


def _fetch_submission_file(name: str, user_agent: str) -> JsonDict:
    url = f"https://data.sec.gov/submissions/{name}"
    return _fetch_json(url, user_agent)


def _fetch_json(url: str, user_agent: str) -> JsonDict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request) as response:
        raw = response.read()
    try:
        payload: JsonValue = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _find_primary_document(payload: JsonDict, accession: str) -> str | None:
    table = _extract_filing_table(payload)
    accessions = table.get("accessionNumber")
    documents = table.get("primaryDocument")
    if isinstance(accessions, list) and isinstance(documents, list):
        for acc, doc in zip(accessions, documents, strict=False):
            if (
                isinstance(acc, str)
                and acc == accession
                and isinstance(doc, str)
                and doc
            ):
                return doc
    return None


def _normalize_form_type(value: JsonValue) -> JsonValue:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "/" in cleaned:
        cleaned = cleaned.split("/", 1)[0]
    return cleaned


def _find_form_type(payload: JsonDict, accession: JsonValue) -> JsonValue:
    if not isinstance(accession, str):
        return None
    table = _extract_filing_table(payload)
    accessions = table.get("accessionNumber")
    forms = table.get("form")
    if isinstance(accessions, list) and isinstance(forms, list):
        for acc, form_value in zip(accessions, forms, strict=False):
            if (
                isinstance(acc, str)
                and acc == accession
                and isinstance(form_value, str)
                and form_value
            ):
                return form_value
    return None


def _extract_filing_table(payload: JsonDict) -> JsonDict:
    filings_block = coerce_json_dict(payload.get("filings"))
    if filings_block:
        recent = coerce_json_dict(filings_block.get("recent"))
        if recent:
            return recent
    return payload


def _iter_submission_files(payload: JsonDict) -> Iterable[str]:
    filings_block = coerce_json_dict(payload.get("filings"))
    if not filings_block:
        return []
    files_value = filings_block.get("files")
    if not isinstance(files_value, list):
        return []
    names: list[str] = []
    for item in files_value:
        item_dict = coerce_json_dict(item)
        if not item_dict:
            continue
        name = item_dict.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def _download_to_path(url: str, path: Path, user_agent: str) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(request) as response:
        data = response.read()
    path.write_bytes(data)
