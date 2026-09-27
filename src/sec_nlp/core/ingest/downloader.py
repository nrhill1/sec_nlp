# src/sec_nlp/core/ingest/downloader.py
"""Download explicitly selected SEC filings through the shared HTTPX budget.

Submissions metadata is refreshed before applying the requested latest-file
limit. Existing files avoid redundant downloads without hiding new filings.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path

import httpx

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.edgar.transport import (
    fetch_sec_bytes,
    fetch_sec_json,
    sec_sync_session,
)
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.filings import get_cik_for_ticker
from sec_nlp.core.ingest.types import DownloadResult, DownloadResults
from sec_nlp.core.types import coerce_json_dict
from sec_nlp.types import JsonDict, JsonValue


def _success_download_result(
    *, downloaded: int, form_type: str, skipped_existing: int | None = None
) -> DownloadResult:
    """Build a successful download-result payload."""
    result: DownloadResult = {
        "success": True,
        "downloaded": downloaded,
        "form_type": form_type,
    }
    if skipped_existing is not None:
        result["skipped_existing"] = skipped_existing
    return result


def _error_download_result(error: str) -> DownloadResult:
    """Build a failed download-result payload with error metadata."""
    return {
        "success": False,
        "error": error,
        "downloaded": 0,
    }


@sec_sync_session()
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
    forms: Sequence[str] | None = None,
) -> DownloadResults:
    """Refresh submissions metadata and download the newest matching filings.

    Args:
        symbols: Tickers or explicit CIKs to discover independently.
        mode: Filing forms to include.
        work_folder: Destination for the established specialist cache layout.
        company_name: Application name for SEC identification.
        email: Contact address for SEC identification.
        after_date: Inclusive earliest filing date.
        before_date: Inclusive latest filing date.
        limit_per_symbol: Maximum selected filings per symbol across all forms.
        forms: Explicit specialist forms overriding the mode when supplied.

    Returns:
        Per-symbol success/error counts, including already cached selections.
    """
    if limit_per_symbol is not None and limit_per_symbol < 1:
        raise ValueError("limit_per_symbol must be positive")
    requested_forms = tuple(forms) if forms else mode.forms
    results: DownloadResults = {}
    user_agent = f"{company_name} {email}"
    for symbol in sorted(set(symbols)):
        downloaded = 0
        skipped = 0
        try:
            cik = (
                symbol.zfill(10)
                if symbol.isdigit()
                else get_cik_for_ticker(
                    ticker=symbol,
                    company_name=company_name,
                    email=email,
                )
            )
            payload = _fetch_submissions_payload(cik, user_agent)
            rows = _submission_rows(
                payload, requested_forms, after_date, before_date
            )
            for name in _iter_submission_files(payload):
                if (
                    limit_per_symbol is not None
                    and len(rows) >= limit_per_symbol
                ):
                    break
                rows.extend(
                    _submission_rows(
                        _fetch_submission_file(name, user_agent),
                        requested_forms,
                        after_date,
                        before_date,
                    )
                )
            rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
            unique_rows = {row[1]: row for row in rows}
            selected = list(unique_rows.values())[:limit_per_symbol]
            for _, accession, primary, form_type in selected:
                count, cached = _download_accession_files(
                    accession=accession,
                    cik=cik,
                    primary_doc=primary,
                    accession_dir=work_folder
                    / "sec-edgar-filings"
                    / symbol.upper()
                    / form_type.removesuffix("/A")
                    / accession,
                    mode=mode,
                    user_agent=user_agent,
                )
                downloaded += count
                skipped += int(cached == 2)
            results[symbol] = _success_download_result(
                downloaded=downloaded,
                form_type=", ".join(requested_forms),
                skipped_existing=skipped,
            )
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.debug(
                "SEC filing download failed for %s", symbol, exc_info=True
            )
            result = _error_download_result(str(exc))
            result["downloaded"] = downloaded
            results[symbol] = result
    return results


def _submission_rows(
    payload: JsonDict,
    forms: Sequence[str],
    after_date: date | None,
    before_date: date | None,
) -> list[tuple[date, str, str, str]]:
    """Select valid source rows without substituting local cache dates."""
    table = _extract_filing_table(payload)
    columns = [
        table.get(key)
        for key in (
            "accessionNumber",
            "filingDate",
            "primaryDocument",
            "form",
        )
    ]
    if not all(isinstance(column, list) for column in columns):
        raise ValueError("SEC submissions response is missing filing columns")
    accessions, dates, documents, form_values = columns
    if (
        not isinstance(accessions, list)
        or not isinstance(dates, list)
        or not isinstance(documents, list)
        or not isinstance(form_values, list)
    ):
        raise ValueError("Invalid SEC submissions columns")
    rows: list[tuple[date, str, str, str]] = []
    for accession, filed, document, form in zip(
        accessions, dates, documents, form_values, strict=True
    ):
        if not isinstance(form, str) or form not in forms:
            continue
        if (
            not isinstance(accession, str)
            or not isinstance(filed, str)
            or not isinstance(document, str)
        ):
            raise ValueError("Invalid SEC filing row")
        filing_date = date.fromisoformat(filed)
        if (after_date and filing_date < after_date) or (
            before_date and filing_date > before_date
        ):
            continue
        rows.append((filing_date, accession, document, form))
    return rows


@sec_sync_session()
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
        except (httpx.HTTPError, OSError, ValueError) as exc:
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
            payload = submissions_cache.get(cik)
            if payload is None:
                payload = _fetch_submissions_payload(cik, user_agent)
                submissions_cache[cik] = payload
            form_value = _find_form_type(payload, accession)
            if form_value is None:
                for name in _iter_submission_files(payload):
                    extra_payload = supplemental_cache.get(name)
                    if extra_payload is None:
                        extra_payload = _fetch_submission_file(name, user_agent)
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
        except (httpx.HTTPError, OSError, ValueError) as exc:
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
    """Look up primary document."""
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
    """Download filing files for one accession into the target directory."""
    if (
        not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession)
        or not re.fullmatch(r"\d{1,10}", cik)
        or int(cik) == 0
    ):
        raise ValueError("Invalid SEC accession or CIK")
    if (
        not primary_doc
        or "/" in primary_doc
        or "\\" in primary_doc
        or primary_doc in {".", ".."}
    ):
        raise ValueError("Invalid primary document filename")
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
    if (primary_ready or mode == FilingMode.holdings) and skipped_existing < 2:
        downloaded_accessions = 1

    return downloaded_accessions, skipped_existing


def _fetch_submissions_payload(cik: str, user_agent: str) -> JsonDict:
    """Fetch and parse SEC submissions payload for a CIK."""
    if not re.fullmatch(r"\d{1,10}", cik.strip()) or int(cik) == 0:
        raise ValueError("Invalid SEC CIK")
    cik_value = cik.strip().zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_value}.json"
    return _fetch_json(url, user_agent)


def _fetch_submission_file(name: str, user_agent: str) -> JsonDict:
    """Fetch submission file."""
    if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", name):
        raise ValueError("Invalid supplemental submissions filename")
    url = f"https://data.sec.gov/submissions/{name}"
    return _fetch_json(url, user_agent)


def _fetch_json(url: str, user_agent: str) -> JsonDict:
    """Fetch json."""
    payload = fetch_sec_json(url, user_agent)
    if not isinstance(payload, dict):
        raise ValueError("SEC submissions response is not a JSON mapping")
    return dict(payload)


def _find_primary_document(payload: JsonDict, accession: str) -> str | None:
    """Select the primary filing document from filing metadata rows."""
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
    """Normalize form type."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "/" in cleaned:
        cleaned = cleaned.split("/", 1)[0]
    return cleaned


def _find_form_type(payload: JsonDict, accession: JsonValue) -> JsonValue:
    """Find form type."""
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
    """Extract filing table."""
    filings_block = coerce_json_dict(payload.get("filings"))
    if filings_block:
        recent = coerce_json_dict(filings_block.get("recent"))
        if recent:
            return recent
    return payload


def _iter_submission_files(payload: JsonDict) -> Iterable[str]:
    """Iterate known SEC submission file URLs for fallback fetches."""
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
    """Download to path."""
    data = fetch_sec_bytes(url, user_agent)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(data)
    temporary.replace(path)


class FilingDownloader:
    """Serve specialist form downloads using the common SEC request policy.

    This small adapter preserves the established per-symbol filesystem layout
    while routing metadata and document requests through the same provider as
    the interactive workspace. It has no independent network client or timer.

    Attributes:
        company_name: Application name sent to SEC.
        email: Contact address sent to SEC.
        work_folder: Root for cached filing files.
    """

    def __init__(
        self, company_name: str, email: str, work_folder: str | Path
    ) -> None:
        """Construct a specialist adapter without issuing requests.

        Args:
            company_name: Application identity.
            email: Contact address.
            work_folder: Destination for existing specialist cache paths.
        """
        self.company_name = company_name
        self.email = email
        self.work_folder = Path(work_folder)

    def get(
        self,
        form: str,
        ticker_or_cik: str,
        *,
        after: date | str | None = None,
        before: date | str | None = None,
        limit: int | None = None,
        include_amends: bool = False,
        download_details: bool = True,
        accession_numbers_to_skip: set[str] | None = None,
    ) -> int:
        """Discover current metadata and materialize the selected filing files.

        Args:
            form: SEC form, optionally with its amendment suffix.
            ticker_or_cik: Company ticker or explicit CIK.
            after: Inclusive earliest filing date.
            before: Inclusive latest filing date.
            limit: Maximum matching filings selected from source metadata.
            include_amends: Include the corresponding amended form.
            download_details: Retained call argument; readable documents are cached.
            accession_numbers_to_skip: Retained argument; file existence governs reuse.

        Returns:
            Number of selected accessions with newly downloaded content.

        Raises:
            ValueError: If form input or a source response is invalid.
            RuntimeError: If the provider could not finish the symbol download.
        """
        if not re.fullmatch(r"[A-Z0-9 -]+(?:/A)?", form):
            raise ValueError("Invalid SEC form")
        forms = (
            (form, form + "/A")
            if include_amends and not form.endswith("/A")
            else (form,)
        )
        results = download_filings(
            symbols=[ticker_or_cik],
            mode=FilingMode.annual,
            work_folder=self.work_folder,
            company_name=self.company_name,
            email=self.email,
            after_date=date.fromisoformat(after)
            if isinstance(after, str)
            else after,
            before_date=date.fromisoformat(before)
            if isinstance(before, str)
            else before,
            limit_per_symbol=limit,
            forms=forms,
        )
        result = results[ticker_or_cik]
        if not result.get("success"):
            raise RuntimeError(
                result.get("error", "SEC filing download failed")
            )
        return result.get("downloaded", 0)
