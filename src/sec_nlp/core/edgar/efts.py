# src/sec_nlp/core/edgar/efts.py
"""Client for SEC EDGAR Full-Text Search (EFTS) API.

The EFTS API allows searching the full text of SEC filings.
Endpoint: https://efts.sec.gov/LATEST/search-index

Rate limits: SEC requests no more than 10 requests per second.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from sec_nlp.core.infra.logger import logger

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

    async def _make_request(self, url: str) -> dict[str, object]:
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
        data: dict[str, object] = json.loads(body)
        return data

    def _parse_response(
        self, data: dict[str, object], query: str
    ) -> EFTSSearchResponse:
        """Parse EFTS API response into models."""
        # EFTS response structure:
        # {
        #   "query": {"from": 0, "size": 10, "q": "..."},
        #   "hits": {"total": {"value": N}, "hits": [...]}
        # }
        raw_hits_data = data.get("hits")
        hits_data: dict[str, object] = (
            raw_hits_data if isinstance(raw_hits_data, dict) else {}
        )

        raw_total = hits_data.get("total")
        if isinstance(raw_total, dict):
            total_value = raw_total.get("value")
            total = int(total_value) if isinstance(total_value, (int, float)) else 0
        elif isinstance(raw_total, (int, float)):
            total = int(raw_total)
        else:
            total = 0

        raw_hits_list = hits_data.get("hits")
        raw_hits: list[object] = (
            raw_hits_list if isinstance(raw_hits_list, list) else []
        )

        hits: list[EFTSHit] = []
        for raw_hit in raw_hits:
            if not isinstance(raw_hit, dict):
                continue
            try:
                hit = self._parse_hit(raw_hit)
                hits.append(hit)
            except Exception as e:
                logger.warning("Failed to parse EFTS hit: %s", e)
                continue

        raw_query_data = data.get("query")
        query_data: dict[str, object] = (
            raw_query_data if isinstance(raw_query_data, dict) else {}
        )

        raw_start = query_data.get("from")
        start = int(raw_start) if isinstance(raw_start, (int, float)) else 0
        raw_limit = query_data.get("size")
        limit = int(raw_limit) if isinstance(raw_limit, (int, float)) else 10

        return EFTSSearchResponse(
            query=query,
            total=total,
            hits=hits,
            start=start,
            limit=limit,
        )

    def _parse_hit(self, raw: dict[str, object]) -> EFTSHit:
        """Parse a single EFTS hit from raw response."""
        raw_source = raw.get("_source")
        source: dict[str, object] = (
            raw_source if isinstance(raw_source, dict) else {}
        )

        # Extract highlight snippet if available
        raw_highlight = raw.get("highlight")
        snippet = ""
        if isinstance(raw_highlight, dict):
            snippets = raw_highlight.get("text")
            if isinstance(snippets, list) and snippets:
                snippet = " ... ".join(str(s) for s in snippets[:3])

        # Parse filed date
        filed_str = source.get("file_date")
        if not isinstance(filed_str, str):
            filed_str = source.get("filed")
        if isinstance(filed_str, str) and filed_str:
            filed_date = date.fromisoformat(filed_str[:10])
        else:
            filed_date = date.today()

        # Get accession number
        accession_raw = source.get("adsh")
        if not isinstance(accession_raw, str):
            accession_raw = source.get("accession_number")
        accession = str(accession_raw) if accession_raw is not None else ""

        # Normalize accession format (add dashes if missing)
        if accession and "-" not in accession and len(accession) == 18:
            accession = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"

        # Get CIK
        cik_raw = source.get("cik")
        cik = str(cik_raw).zfill(10) if cik_raw is not None else "0000000000"

        # Get company name
        display_names = source.get("display_names")
        if isinstance(display_names, list) and display_names:
            company_name = str(display_names[0])
        else:
            company_raw = source.get("company")
            company_name = str(company_raw) if company_raw is not None else ""

        # Get form type
        form_raw = source.get("form")
        form_type = str(form_raw) if form_raw is not None else ""

        # Get optional fields
        file_num = source.get("file_num")
        file_number = file_num if isinstance(file_num, str) else None

        film_num = source.get("film_num")
        film_number = film_num if isinstance(film_num, str) else None

        # Get score
        score_raw = raw.get("_score")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0

        return EFTSHit(
            accession_number=accession,
            cik=cik,
            company_name=company_name,
            form_type=form_type,
            filed_date=filed_date,
            file_number=file_number,
            film_number=film_number,
            snippet=snippet,
            score=score,
            filing_url=None,  # Computed via edgar_url property
        )


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
