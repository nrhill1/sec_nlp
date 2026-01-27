# src/sec_nlp/core/edgar/efts.py
"""Client for SEC EDGAR Full-Text Search (EFTS) API.

The EFTS API allows searching the full text of SEC filings.
Endpoint: https://efts.sec.gov/LATEST/search-index

Rate limits: SEC requests no more than 10 requests per second.

Set SEC_NLP_EFTS_BACKEND=rust to use the efts Rust extension when
available.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.types import as_json_dict
from sec_nlp.types import JsonArray, JsonDict, JsonValue

from .efts_models import (
    EFTSError,
    EFTSHit,
    EFTSSearchParams,
    EFTSSearchResponse,
    EFTSSortField,
    EFTSSortOrder,
)

EFTS_BASE_URL: Final[str] = "https://efts.sec.gov/LATEST/search-index"
DEFAULT_USER_AGENT: Final[str] = "SEC NLP Tool (contact@example.com)"
MIN_REQUEST_INTERVAL: Final[float] = 0.1  # 10 requests per second max
_CIK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bCIK\s*(\d{1,10})\b",
    re.IGNORECASE,
)
_INSIDER_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}
_COMPANY_KEYWORDS = (
    " INC",
    " INC.",
    " CORP",
    " CORPORATION",
    " LTD",
    " LIMITED",
    " LLC",
    " PLC",
    " LP",
    " L.P.",
    " LLP",
    " CO",
    " COMPANY",
    " HOLDINGS",
    " GROUP",
    " TRUST",
    " FUND",
    " RESOURCES",
    " MINING",
    " MATERIALS",
    " ENERGY",
    " TECHNOLOGIES",
    " SYSTEMS",
    " ENTERPRISES",
)

_EFTS_RUST_BACKEND_ENV = "SEC_NLP_EFTS_BACKEND"


def _rust_backend_enabled() -> bool:
    # Opt-in via SEC_NLP_EFTS_BACKEND=rust.
    value = os.getenv(_EFTS_RUST_BACKEND_ENV)
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "rust", "on"}


@lru_cache(maxsize=1)
def _load_efts_module() -> ModuleType | None:
    try:
        return import_module("efts")
    except Exception as exc:  # pragma: no cover - depends on extension install
        logger.debug("efts import failed: %s", exc)
        return None


class EFTSClientConfig(BaseModel):
    """Configuration for EFTS client."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    base_url: str = Field(
        default=EFTS_BASE_URL,
        description="Base URL for EFTS API",
    )
    user_agent: str = Field(
        default=DEFAULT_USER_AGENT,
        description="User-Agent header for SEC requests (should include contact email)",
    )
    timeout: float = Field(
        default=30.0,
        gt=0,
        description="Request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed requests",
    )
    retry_delay: float = Field(
        default=1.0,
        ge=0,
        description="Initial delay between retries (doubles each attempt)",
    )
    rate_limit_delay: float = Field(
        default=MIN_REQUEST_INTERVAL,
        ge=0,
        description="Minimum delay between requests to respect SEC rate limits",
    )


class EFTSClient(BaseModel):
    """Async client for SEC EDGAR Full-Text Search API.

    Example:
        client = EFTSClient(config=EFTSClientConfig(
            user_agent="MyApp (me@example.com)"
        ))
        response = await client.search("warranty accrual", forms=["10-K"])
        for hit in response.hits:
            print(f"{hit.company_name}: {hit.accession_number}")
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
    )

    config: EFTSClientConfig = Field(
        default_factory=EFTSClientConfig,
        description="Client configuration",
    )

    _last_request_time: float = PrivateAttr(default=0.0)
    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    async def search(
        self,
        query: str,
        *,
        forms: Sequence[str] | None = None,
        ciks: Sequence[str] | None = None,
        tickers: Sequence[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 10,
        start: int = 0,
        sort_field: EFTSSortField = EFTSSortField.relevance,
        sort_order: EFTSSortOrder = EFTSSortOrder.desc,
    ) -> EFTSSearchResponse:
        """Execute a full-text search against SEC EFTS.

        Args:
            query: Search query string
            forms: Optional form types to filter (e.g., ["10-K", "8-K"])
            ciks: Optional CIK numbers to filter
            tickers: Optional ticker symbols to filter
            start_date: Optional start date for filing date range
            end_date: Optional end date for filing date range
            limit: Maximum results to return (1-100)
            start: Pagination offset
            sort_field: Field to sort by (relevance or filed date)
            sort_order: Sort direction (asc or desc)

        Returns:
            EFTSSearchResponse containing hits and pagination info

        Raises:
            EFTSAPIError: If the API returns an error or request fails
        """
        params = EFTSSearchParams(
            query=query,
            forms=list(forms) if forms else [],
            ciks=list(ciks) if ciks else [],
            tickers=list(tickers) if tickers else [],
            start_date=start_date,
            end_date=end_date,
            limit=min(limit, 100),
            start=start,
            sort_field=sort_field,
            sort_order=sort_order,
        )

        return await self._execute_search(params)

    async def search_all(
        self,
        query: str,
        *,
        forms: Sequence[str] | None = None,
        ciks: Sequence[str] | None = None,
        tickers: Sequence[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        max_results: int = 100,
        sort_field: EFTSSortField = EFTSSortField.relevance,
        sort_order: EFTSSortOrder = EFTSSortOrder.desc,
    ) -> list[EFTSHit]:
        """Fetch all results up to max_results, handling pagination.

        Args:
            query: Search query string
            forms: Optional form types to filter
            ciks: Optional CIK numbers to filter
            tickers: Optional ticker symbols to filter
            start_date: Optional start date for filing date range
            end_date: Optional end date for filing date range
            max_results: Maximum total results to fetch
            sort_field: Field to sort by
            sort_order: Sort direction

        Returns:
            List of all EFTSHit results up to max_results
        """
        all_hits: list[EFTSHit] = []
        offset = 0
        page_size = min(100, max_results)

        while len(all_hits) < max_results:
            remaining = max_results - len(all_hits)
            fetch_size = min(page_size, remaining)

            response = await self.search(
                query,
                forms=forms,
                ciks=ciks,
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                limit=fetch_size,
                start=offset,
                sort_field=sort_field,
                sort_order=sort_order,
            )

            all_hits.extend(response.hits)

            if not response.has_more or not response.hits:
                break

            offset = response.next_offset

        return all_hits[:max_results]

    async def _execute_search(
        self, params: EFTSSearchParams
    ) -> EFTSSearchResponse:
        """Execute search with rate limiting and retries."""
        rust_response = await self._try_rust_search(params)
        if rust_response is not None:
            return rust_response

        await self._rate_limit()

        api_params = params.to_api_params()
        url = self._build_url(api_params)

        logger.debug("EFTS search: %s", url)

        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response_data = await self._make_request(url)
                return self._parse_response(response_data, params.query)
            except EFTSAPIError as e:
                last_error = e
                if e.status_code == 429:  # Rate limited
                    delay = self.config.retry_delay * (2**attempt)
                    logger.warning(
                        "EFTS rate limited, waiting %.1fs (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        self.config.max_retries + 1,
                    )
                    await asyncio.sleep(delay)
                elif e.status_code >= 500:  # Server error, retry
                    delay = self.config.retry_delay * (2**attempt)
                    logger.warning(
                        "EFTS server error %d, retrying in %.1fs (attempt %d/%d)",
                        e.status_code,
                        delay,
                        attempt + 1,
                        self.config.max_retries + 1,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            except (urllib.error.URLError, TimeoutError) as e:
                last_error = EFTSAPIError(
                    status_code=0,
                    message=f"Network error: {e}",
                )
                delay = self.config.retry_delay * (2**attempt)
                logger.warning(
                    "EFTS network error, retrying in %.1fs (attempt %d/%d): %s",
                    delay,
                    attempt + 1,
                    self.config.max_retries + 1,
                    e,
                )
                await asyncio.sleep(delay)

        if last_error:
            raise last_error
        raise EFTSAPIError(status_code=0, message="Unknown error after retries")

    async def _try_rust_search(
        self,
        params: EFTSSearchParams,
    ) -> EFTSSearchResponse | None:
        if not _rust_backend_enabled():
            return None

        module = _load_efts_module()
        if module is None:
            raise EFTSAPIError(
                status_code=0,
                message="efts extension is not available; "
                "build it with `make rs-sg-dev`.",
            )

        try:
            return await asyncio.to_thread(
                _rust_execute_search,
                module,
                self.config,
                params,
            )
        except EFTSAPIError:
            raise
        except Exception as exc:
            raise _rust_error_from_exception(exc) from exc

    async def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        async with self._lock:
            import time

            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.config.rate_limit_delay:
                await asyncio.sleep(self.config.rate_limit_delay - elapsed)
            self._last_request_time = time.monotonic()

    def _build_url(self, params: dict[str, str | int]) -> str:
        """Build the full URL with query parameters."""
        encoded = urllib.parse.urlencode(params)
        return f"{self.config.base_url}?{encoded}"

    async def _make_request(self, url: str) -> JsonDict:
        """Make HTTP request to EFTS API."""
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json",
        }
        request = urllib.request.Request(url, headers=headers)

        # Run blocking I/O in thread pool
        loop = asyncio.get_event_loop()
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: urllib.request.urlopen(
                        request, timeout=self.config.timeout
                    ),
                ),
                timeout=self.config.timeout + 5,
            )
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            raise EFTSAPIError(
                status_code=e.code,
                message=f"HTTP {e.code}: {e.reason}",
                detail=body if body else None,
            ) from e
        except urllib.error.URLError as e:
            raise EFTSAPIError(
                status_code=0,
                message=f"URL error: {e.reason}",
            ) from e

        body = response.read().decode("utf-8")
        data: JsonDict = json.loads(body)
        return data

    def _parse_response(self, data: JsonDict, query: str) -> EFTSSearchResponse:
        """Parse EFTS API response into models."""
        # EFTS response structure:
        # {
        #   "query": {"from": 0, "size": 10, "q": "..."},
        #   "hits": {"total": {"value": N}, "hits": [...]}
        # }
        hits_data = _get_dict(data, "hits")
        total = _extract_total(hits_data)
        raw_hits = _get_list(hits_data, "hits")

        hits: list[EFTSHit] = []
        for raw_hit in raw_hits:
            parsed = as_json_dict(raw_hit)
            if parsed is None:
                continue
            try:
                hit = self._parse_hit(parsed)
                hits.append(hit)
            except Exception as e:
                logger.warning("Failed to parse EFTS hit: %s", e)
                continue

        query_data = _get_dict(data, "query")
        start = _get_int(query_data, "from", 0)
        limit = _get_int(query_data, "size", 10)

        return EFTSSearchResponse(
            query=query,
            total=total,
            hits=hits,
            start=start,
            limit=limit,
        )

    def _parse_hit(self, raw: JsonDict) -> EFTSHit:
        """Parse a single EFTS hit from raw response."""
        source = _get_dict(raw, "_source")
        snippet = _extract_snippet(raw)
        filed_date = _extract_filed_date(source)
        accession = _extract_accession(source)
        company_name = _extract_company_name(source)
        tickers = _extract_tickers(source, company_name)
        cik = _extract_cik(source, company_name, accession)
        form_type = _get_str(source, "form", "")
        file_number = _get_optional_str(source, "file_num")
        film_number = _get_optional_str(source, "film_num")
        score = _get_float(raw, "_score", 0.0)

        return EFTSHit(
            accession_number=accession,
            cik=cik,
            company_name=company_name,
            tickers=tickers,
            form_type=form_type,
            filed_date=filed_date,
            file_number=file_number,
            film_number=film_number,
            snippet=snippet,
            score=score,
            filing_url=None,  # Computed via edgar_url property
        )


# -- Helper functions for type-safe JSON parsing --


def _rust_error_from_exception(exc: Exception) -> EFTSAPIError:
    message = str(exc)
    match = re.search(r"EFTS API Error \((\d+)\):\s*(.+)", message)
    if match:
        status_code = int(match.group(1))
        text = match.group(2)
        detail = None
        if "; " in text:
            text, detail = text.split("; ", 1)
        return EFTSAPIError(
            status_code=status_code,
            message=text,
            detail=detail,
        )
    return EFTSAPIError(status_code=0, message=message)


def _rust_execute_search(
    module: ModuleType,
    config: EFTSClientConfig,
    params: EFTSSearchParams,
) -> EFTSSearchResponse:
    forms = params.forms if params.forms else None
    ciks = params.ciks if params.ciks else None
    tickers = params.tickers if params.tickers else None
    start_date = params.start_date.isoformat() if params.start_date else None
    end_date = params.end_date.isoformat() if params.end_date else None

    client = module.EFTSClient(
        user_agent=config.user_agent,
        timeout=config.timeout,
        max_retries=config.max_retries,
        retry_delay=config.retry_delay,
        rate_limit_delay=config.rate_limit_delay,
        base_url=config.base_url,
    )
    response = client.search(
        params.query,
        forms=forms,
        ciks=ciks,
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        limit=params.limit,
        start=params.start,
        sort_field=params.sort_field.value,
        sort_order=params.sort_order.value,
    )
    normalized = as_json_dict(response)
    if normalized is None:
        raise EFTSAPIError(
            status_code=0,
            message="Rust EFTS response was not JSON",
        )
    return EFTSSearchResponse.model_validate(normalized)


def _get_dict(data: JsonDict, key: str) -> JsonDict:
    """Extract a dict value from JSON data."""
    val = data.get(key)
    if isinstance(val, dict):
        return dict(val)
    return {}


def _get_list(data: JsonDict, key: str) -> JsonArray:
    """Extract a list value from JSON data."""
    val = data.get(key)
    if isinstance(val, list):
        return list(val)
    return []


def _get_str(data: JsonDict, key: str, default: str) -> str:
    """Extract a string value from JSON data."""
    val = data.get(key)
    if val is None:
        return default
    return str(val)


def _get_optional_str(data: JsonDict, key: str) -> str | None:
    """Extract an optional string value from JSON data."""
    val = data.get(key)
    if isinstance(val, str):
        return val
    return None


def _get_int(data: JsonDict, key: str, default: int) -> int:
    """Extract an int value from JSON data."""
    val = data.get(key)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    return default


def _get_float(data: JsonDict, key: str, default: float) -> float:
    """Extract a float value from JSON data."""
    val = data.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return default


def _extract_total(hits_data: JsonDict) -> int:
    """Extract total count from hits data."""
    raw_total = hits_data.get("total")
    if isinstance(raw_total, dict):
        total_dict: JsonDict = dict(raw_total)
        val = total_dict.get("value")
        if isinstance(val, (int, float)):
            return int(val)
        return 0
    if isinstance(raw_total, (int, float)):
        return int(raw_total)
    return 0


def _extract_snippet(raw: JsonDict) -> str:
    """Extract highlight snippet from hit."""
    raw_highlight = raw.get("highlight")
    if not isinstance(raw_highlight, dict):
        return ""
    highlight_dict: JsonDict = dict(raw_highlight)
    snippets = highlight_dict.get("text")
    if isinstance(snippets, list) and snippets:
        return " ... ".join(str(s) for s in snippets[:3])
    return ""


def _extract_filed_date(source: JsonDict) -> date:
    """Extract filed date from source."""
    filed_str = source.get("file_date")
    if not isinstance(filed_str, str):
        filed_str = source.get("filed")
    if isinstance(filed_str, str) and filed_str:
        return date.fromisoformat(filed_str[:10])
    return date.today()


def _extract_accession(source: JsonDict) -> str:
    """Extract and normalize accession number."""
    accession_raw = source.get("adsh")
    if not isinstance(accession_raw, str):
        accession_raw = source.get("accession_number")
    accession = str(accession_raw) if accession_raw is not None else ""
    # Normalize format (add dashes if missing)
    if accession and "-" not in accession and len(accession) == 18:
        return f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
    return accession


def _extract_company_name(source: JsonDict) -> str:
    """Extract company name from source."""
    form_type = _get_str(source, "form", "")
    normalized_form = form_type.replace(" ", "").upper()
    company_raw = source.get("company")
    display_names = source.get("display_names")

    if normalized_form in _INSIDER_FORMS:
        if isinstance(company_raw, str):
            company_name = company_raw.strip()
            if company_name:
                return company_name
        if isinstance(display_names, list) and display_names:
            best_name = ""
            best_score = -100
            for item in display_names:
                if not isinstance(item, str):
                    continue
                name = item.strip()
                if not name:
                    continue
                upper = name.upper()
                score = 0
                if "CIK" not in upper:
                    score += 2
                if "(" in name and ")" in name and "CIK" not in upper:
                    score += 1
                if "," in name:
                    score -= 1
                for keyword in _COMPANY_KEYWORDS:
                    if keyword in upper:
                        score += 2
                        break
                if score > best_score:
                    best_score = score
                    best_name = name
            if best_name:
                return best_name

    if isinstance(display_names, list) and display_names:
        return str(display_names[0])
    if company_raw is not None:
        return str(company_raw)
    return ""


def _extract_tickers(source: JsonDict, company_name: str) -> list[str]:
    """Extract ticker symbols from EFTS source data or company name."""
    tickers: list[str] = []

    raw_tickers = source.get("tickers")
    if isinstance(raw_tickers, list):
        for item in raw_tickers:
            if isinstance(item, str):
                _append_ticker(tickers, item)
    elif isinstance(raw_tickers, str):
        for item in re.split(r"[,\s/]+", raw_tickers):
            _append_ticker(tickers, item)

    raw_ticker = source.get("ticker")
    if isinstance(raw_ticker, str):
        _append_ticker(tickers, raw_ticker)

    if not tickers:
        tickers = _extract_tickers_from_company(company_name)

    return tickers


def _extract_tickers_from_company(company_name: str) -> list[str]:
    """Parse tickers from the company display string."""
    tickers: list[str] = []
    if not company_name:
        return tickers
    for match in re.findall(r"\(([^)]+)\)", company_name):
        for raw in re.split(r"[,/]", match):
            cleaned = raw.strip()
            if not cleaned:
                continue
            if "CIK" in cleaned.upper():
                continue
            _append_ticker(tickers, cleaned)
    return tickers


def _append_ticker(tickers: list[str], value: str) -> None:
    cleaned = _normalize_ticker(value)
    if cleaned and cleaned not in tickers:
        tickers.append(cleaned)


def _normalize_ticker(value: str) -> str | None:
    cleaned = value.strip().upper().strip("()[]{}")
    if not cleaned:
        return None
    if "CIK" in cleaned:
        return None
    if ":" in cleaned:
        suffix = cleaned.split(":")[-1].strip()
        if suffix:
            cleaned = suffix
    if not any(ch.isalpha() for ch in cleaned):
        return None
    if len(cleaned) > 10:
        return None
    return cleaned


def _extract_cik(
    source: JsonDict,
    company_name: str,
    accession: str,
) -> str:
    """Extract a CIK using multiple fallback strategies."""
    candidate = _coerce_cik(source.get("cik"))
    if candidate is not None:
        return candidate

    ciks_raw = source.get("ciks")
    if isinstance(ciks_raw, list):
        for item in ciks_raw:
            candidate = _coerce_cik(item)
            if candidate is not None:
                return candidate

    candidate = _extract_cik_from_company(company_name)
    if candidate is not None:
        return candidate

    candidate = _extract_cik_from_accession(accession)
    if candidate is not None:
        return candidate

    return "0000000000"


def _coerce_cik(value: JsonValue) -> str | None:
    """Normalize a CIK value to a zero-padded 10-digit string."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        raw = str(value)
    elif isinstance(value, float):
        raw = str(int(value))
    elif isinstance(value, str):
        raw = value.strip()
    else:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    if len(digits) > 10:
        digits = digits[-10:]
    cik = digits.zfill(10)
    if cik == "0000000000":
        return None
    return cik


def _extract_cik_from_company(company_name: str) -> str | None:
    """Pull a CIK from display/company name strings when present."""
    if not company_name:
        return None
    match = _CIK_PATTERN.search(company_name)
    if not match:
        return None
    return _coerce_cik(match.group(1))


def _extract_cik_from_accession(accession: str) -> str | None:
    """Derive a CIK from the accession prefix when available."""
    if not accession:
        return None
    prefix = accession.split("-", 1)[0]
    return _coerce_cik(prefix)


class EFTSAPIError(Exception):
    """Error from EFTS API request."""

    def __init__(
        self,
        status_code: int,
        message: str,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.detail = detail
        super().__init__(f"EFTS API Error ({status_code}): {message}")

    def to_model(self) -> EFTSError:
        """Convert to EFTSError model."""
        return EFTSError(
            status=self.status_code,
            message=self.message,
            detail=self.detail,
        )


def create_efts_client(
    *,
    email: str,
    company_name: str = "SEC NLP Tool",
    timeout: float = 30.0,
) -> EFTSClient:
    """Create an EFTS client with proper user agent.

    Args:
        email: Contact email for SEC user agent (required)
        company_name: Application name for user agent
        timeout: Request timeout in seconds

    Returns:
        Configured EFTSClient instance
    """
    config = EFTSClientConfig(
        user_agent=f"{company_name} ({email})",
        timeout=timeout,
    )
    return EFTSClient(config=config)
