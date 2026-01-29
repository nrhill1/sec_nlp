# src/sec_nlp/core/edgar/efts.py
"""Client for SEC EDGAR Full-Text Search (EFTS) API.

The EFTS API allows searching the full text of SEC filings.
Endpoint: https://efts.sec.gov/LATEST/search-index

Rate limits: SEC requests no more than 10 requests per second.

EFTS searches are executed via the Rust extension.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

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

        Uses the Rust async search_all implementation for efficient pagination.

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
        module = _load_efts_module()
        if module is None:
            raise EFTSAPIError(
                status_code=0,
                message="efts extension is not available; "
                "build it with `make rs-sg-dev`.",
            )

        try:
            return await _rust_execute_search_all_async(
                module,
                self.config,
                query,
                forms,
                ciks,
                tickers,
                start_date,
                end_date,
                max_results,
                sort_field,
                sort_order,
            )
        except EFTSAPIError:
            raise
        except Exception as exc:
            raise _rust_error_from_exception(exc) from exc

    async def _execute_search(
        self, params: EFTSSearchParams
    ) -> EFTSSearchResponse:
        """Execute search with rate limiting and retries."""
        return await self._try_rust_search(params)

    async def _try_rust_search(
        self,
        params: EFTSSearchParams,
    ) -> EFTSSearchResponse:
        module = _load_efts_module()
        if module is None:
            raise EFTSAPIError(
                status_code=0,
                message="efts extension is not available; "
                "build it with `make rs-sg-dev`.",
            )

        try:
            return await _rust_execute_search_async(
                module,
                self.config,
                params,
            )
        except EFTSAPIError:
            raise
        except Exception as exc:
            raise _rust_error_from_exception(exc) from exc


# -- Helper functions for the Rust extension --


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


async def _rust_execute_search_async(
    module: ModuleType,
    config: EFTSClientConfig,
    params: EFTSSearchParams,
) -> EFTSSearchResponse:
    """Execute search using native Rust async method."""
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
    # Use native async method - returns awaitable
    rust_response = await client.search_async(
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
    return _convert_rust_response(rust_response)


def _rust_execute_search(
    module: ModuleType,
    config: EFTSClientConfig,
    params: EFTSSearchParams,
) -> EFTSSearchResponse:
    """Execute search using blocking Rust method (for sync callers)."""
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
    rust_response = client.search(
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
    return _convert_rust_response(rust_response)


def _convert_rust_response(rust_response: object) -> EFTSSearchResponse:
    """Convert Rust EFTSSearchResponse to Pydantic model."""
    # Convert Rust EFTSHit objects to Pydantic EFTSHit models
    hits = [
        EFTSHit(
            accession_number=hit.accession_number,
            cik=hit.cik,
            company_name=hit.company_name,
            tickers=list(hit.tickers),
            form_type=hit.form_type,
            filed_date=hit.filed_date,
            file_number=hit.file_number,
            film_number=hit.film_number,
            snippet=hit.snippet,
            score=hit.score,
            filing_url=hit.filing_url,
        )
        for hit in rust_response.hits  # type: ignore[attr-defined]
    ]
    return EFTSSearchResponse(
        query=rust_response.query,  # type: ignore[attr-defined]
        total=rust_response.total,  # type: ignore[attr-defined]
        hits=hits,
        start=rust_response.start,  # type: ignore[attr-defined]
        limit=rust_response.limit,  # type: ignore[attr-defined]
    )


def _convert_rust_hit(hit: object) -> EFTSHit:
    """Convert a single Rust EFTSHit to Pydantic model."""
    return EFTSHit(
        accession_number=hit.accession_number,  # type: ignore[attr-defined]
        cik=hit.cik,  # type: ignore[attr-defined]
        company_name=hit.company_name,  # type: ignore[attr-defined]
        tickers=list(hit.tickers),  # type: ignore[attr-defined]
        form_type=hit.form_type,  # type: ignore[attr-defined]
        filed_date=hit.filed_date,  # type: ignore[attr-defined]
        file_number=hit.file_number,  # type: ignore[attr-defined]
        film_number=hit.film_number,  # type: ignore[attr-defined]
        snippet=hit.snippet,  # type: ignore[attr-defined]
        score=hit.score,  # type: ignore[attr-defined]
        filing_url=hit.filing_url,  # type: ignore[attr-defined]
    )


async def _rust_execute_search_all_async(
    module: ModuleType,
    config: EFTSClientConfig,
    query: str,
    forms: Sequence[str] | None,
    ciks: Sequence[str] | None,
    tickers: Sequence[str] | None,
    start_date: date | None,
    end_date: date | None,
    max_results: int,
    sort_field: EFTSSortField,
    sort_order: EFTSSortOrder,
) -> list[EFTSHit]:
    """Execute search_all using native Rust async method."""
    forms_list = list(forms) if forms else None
    ciks_list = list(ciks) if ciks else None
    tickers_list = list(tickers) if tickers else None
    start_date_str = start_date.isoformat() if start_date else None
    end_date_str = end_date.isoformat() if end_date else None

    client = module.EFTSClient(
        user_agent=config.user_agent,
        timeout=config.timeout,
        max_retries=config.max_retries,
        retry_delay=config.retry_delay,
        rate_limit_delay=config.rate_limit_delay,
        base_url=config.base_url,
    )
    # Use native async method - returns awaitable
    rust_hits = await client.search_all_async(
        query,
        forms=forms_list,
        ciks=ciks_list,
        tickers=tickers_list,
        start_date=start_date_str,
        end_date=end_date_str,
        max_results=max_results,
        sort_field=sort_field.value,
        sort_order=sort_order.value,
    )
    return [_convert_rust_hit(hit) for hit in rust_hits]


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


if __name__ == "__main__":
    """Entry point when running as: python -m sec_nlp.core.edgar.efts"""
    import sys

    # Inject 'efts' as a subcommand into sys.argv for the CLI framework
    if len(sys.argv) > 1:
        sys.argv.insert(1, "efts")
    else:
        sys.argv = ["sec-nlp", "efts"]

    from sec_nlp.cli.__main__ import main

    sys.exit(main())
