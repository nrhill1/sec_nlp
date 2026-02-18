"""Helpers for locating, parsing, and extracting SEC filings on disk."""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Iterable
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from langchain_core.documents import Document

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import logger


def filing_dir(base: Path, symbol: str, mode: FilingMode) -> Path:
    """Build the path to a symbol's filing directory on disk."""
    return base / "sec-edgar-filings" / symbol.upper() / mode.form


def get_filing_date_from_dir(filing_dir_path: Path) -> date | None:
    """Extract filing date from full-submission.txt in filing directory."""
    submission_file = filing_dir_path / "full-submission.txt"
    if not submission_file.exists():
        return None

    try:
        with open(submission_file, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("FILED AS OF DATE:"):
                    # Format: FILED AS OF DATE:		20201217
                    date_str = line.split(":")[-1].strip()
                    return date(
                        int(date_str[:4]),
                        int(date_str[4:6]),
                        int(date_str[6:8]),
                    )
    except Exception as exc:
        logger.debug(
            "Failed to parse filing date from %s: %s", submission_file, exc
        )
    return None


def html_paths_for_symbol(
    *,
    symbol: str,
    mode: FilingMode,
    base: Path,
    limit: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Path]:
    """Get HTML file paths for a symbol, optionally filtered by date range."""
    symbol_root = base / "sec-edgar-filings" / symbol.upper()
    form_dirs = [symbol_root / form for form in mode.forms]
    existing_form_dirs = [path for path in form_dirs if path.exists()]
    if not existing_form_dirs:
        forms_label = ", ".join(mode.forms)
        raise FileNotFoundError(
            f"No filings found for {symbol} in mode {mode.value} "
            f"(forms: {forms_label}) under {symbol_root}"
        )

    html_files_with_dates: list[tuple[Path, date | None]] = []
    for form_dir in existing_form_dirs:
        for html_path in form_dir.rglob("*"):
            if not html_path.is_file():
                continue
            if html_path.suffix.lower() not in {".html", ".htm", ".xhtml"}:
                continue
            accession_dir = html_path.parent
            filing_date = get_filing_date_from_dir(accession_dir)
            html_files_with_dates.append((html_path, filing_date))

    if start_date or end_date:
        filtered: list[tuple[Path, date | None]] = []
        for html_path, filing_date in html_files_with_dates:
            if filing_date is None:
                filtered.append((html_path, filing_date))
                continue
            if start_date and filing_date < start_date:
                continue
            if end_date and filing_date > end_date:
                continue
            filtered.append((html_path, filing_date))
        html_files_with_dates = filtered

    def sort_key(item: tuple[Path, date | None]) -> tuple[date, float]:
        html_path, filing_date = item
        if filing_date:
            return (filing_date, 0.0)
        return (date.min, -html_path.stat().st_mtime)

    html_files_with_dates.sort(key=sort_key, reverse=True)
    html_files = [path for path, _ in html_files_with_dates]
    return html_files[:limit] if limit else html_files


class _TickerEntry(TypedDict):
    cik: str
    company_name: str


@lru_cache(maxsize=4)
def _load_ticker_registry(
    company_name: str, email: str
) -> dict[str, _TickerEntry]:
    logger.debug("Fetching ticker-to-CIK mapping from SEC...")
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {"User-Agent": f"{company_name} {email}"}
    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())

    registry: dict[str, _TickerEntry] = {}
    for entry in data.values():
        ticker_symbol = entry.get("ticker", "").upper()
        cik_num = entry.get("cik_str")
        company_title = str(entry.get("title", "")).strip()
        if ticker_symbol and cik_num:
            registry[ticker_symbol] = _TickerEntry(
                cik=str(cik_num).zfill(10),
                company_name=company_title,
            )

    logger.debug("Loaded %d ticker registry entries", len(registry))
    return registry


def get_cik_for_ticker(*, ticker: str, company_name: str, email: str) -> str:
    """Look up CIK for a ticker symbol from SEC."""
    try:
        registry = _load_ticker_registry(company_name, email)
    except Exception as exc:
        logger.error("Failed to fetch ticker-to-CIK mapping: %s", exc)
        raise

    key = ticker.upper()
    if key not in registry:
        raise ValueError(
            f"Could not find CIK for ticker {ticker}. "
            "Ticker may not exist or may not be in SEC database."
        )

    return registry[key]["cik"]


def get_company_name_for_ticker(
    *,
    ticker: str,
    company_name: str,
    email: str,
) -> str | None:
    """Look up issuer company name for a ticker symbol from SEC.

    Returns ``None`` when the ticker is not found or has no title.
    """

    registry = _load_ticker_registry(company_name, email)
    entry = registry.get(ticker.upper())
    if entry is None:
        return None

    company_title = entry.get("company_name", "").strip()
    return company_title or None


def load_xbrl_facts(
    *,
    symbols: Iterable[str],
    tags: list[str],
    mode: FilingMode,
    downloads_folder: Path,
    limit_per_symbol: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Document]:
    """Extract Inline XBRL facts from downloaded filing HTML/XML files."""
    facts: list[Document] = []
    for symbol in sorted(symbols):
        try:
            html_paths = html_paths_for_symbol(
                symbol=symbol,
                mode=mode,
                base=downloads_folder,
                limit=limit_per_symbol,
                start_date=start_date,
                end_date=end_date,
            )
        except FileNotFoundError:
            logger.warning(
                "No filings found on disk for %s (%s)", symbol, mode.value
            )
            continue

        for path in html_paths:
            try:
                text = path.read_text(errors="ignore")
            except Exception as exc:  # pragma: no cover - file read issues
                logger.error("Failed to read %s: %s", path.name, exc)
                continue

            accession_number = None
            acc_match = re.search(r"/([0-9]{10}-[0-9]{2}-[0-9]{6})/", str(path))
            if acc_match:
                accession_number = acc_match.group(1)

            for tag in tags:
                for match in re.finditer(
                    rf'<ix:nonFraction[^>]*name="{re.escape(tag)}"[^>]*>([-+]?\d[\d,\.]*)</ix:nonFraction>',
                    text,
                    flags=re.IGNORECASE,
                ):
                    element = match.group(0)
                    raw_val = match.group(1)
                    scale = 0
                    scale_match = re.search(r'scale="(-?\d+)"', element)
                    if scale_match:
                        try:
                            scale = int(scale_match.group(1))
                        except ValueError:
                            scale = 0
                    try:
                        val = float(raw_val.replace(",", ""))
                        if scale:
                            val *= 10**scale
                    except ValueError:
                        continue

                    context_ref = None
                    period_end = None
                    fiscal_year = None
                    context_match = re.search(r'contextRef="([^"]+)"', element)
                    if context_match:
                        context_ref = context_match.group(1)
                        date_match = re.search(
                            r"As_Of_(\d{1,2})_(\d{1,2})_(\d{4})",
                            context_ref,
                        )
                        if date_match:
                            month, day, year = date_match.groups()
                            period_end = (
                                f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                            )
                            fiscal_year = year

                    meta = {
                        "tag": tag,
                        "source": str(path),
                        "scale": scale,
                        "raw_value": raw_val,
                        "category": "xbrl",
                        "symbol": symbol,
                        "accession_number": accession_number,
                        "context_ref": context_ref,
                        "period_end": period_end,
                        "fiscal_year": fiscal_year,
                    }
                    facts.append(
                        Document(
                            page_content=str(val),
                            metadata=meta,
                        )
                    )

    return facts
