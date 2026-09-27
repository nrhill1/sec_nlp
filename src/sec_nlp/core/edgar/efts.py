# src/sec_nlp/core/edgar/efts.py
"""Client for SEC EDGAR Full-Text Search (EFTS) API.

The EFTS API allows searching the full text of SEC filings.
Endpoint: https://efts.sec.gov/LATEST/search-index

Rate limits: SEC requests no more than 10 requests per second.

HTTPX owns all requests under the shared SEC rate budget. The native extension
only parses downloaded responses and provides optional keyword ranking.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from .efts_models import (
    EFTSBatchResult,
    EFTSError,
    EFTSHit,
    EFTSSearchParams,
    EFTSSearchResponse,
    EFTSSortField,
    EFTSSortOrder,
)
from .filing_models import FilingEntity
from .transport import SecTransport

logger = logging.getLogger(__name__)

EFTS_BASE_URL: Final[str] = "https://efts.sec.gov/LATEST/search-index"
DEFAULT_USER_AGENT: Final[str] = "SEC NLP Tool (contact@example.com)"
MIN_REQUEST_INTERVAL: Final[float] = 0.2  # Shared app budget: 5 per second
_JSON = TypeAdapter(JsonValue)
_DISPLAY_CIK = re.compile(r"\(\s*CIK\s+(\d{1,10})\s*\)", re.IGNORECASE)


def _source_entities(source: dict[str, JsonValue]) -> tuple[FilingEntity, ...]:
    """Preserve explicit CIKs and names that identify their own matching CIK."""
    ciks: dict[str, str] = {}
    candidates = source.get("ciks")
    values = list(candidates) if isinstance(candidates, list) else []
    values.append(source.get("cik"))
    for value in values:
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            cleaned = str(value).strip()
            if re.fullmatch(r"\d{1,10}", cleaned) and int(cleaned) > 0:
                ciks.setdefault(cleaned.zfill(10), "")
    display_names = source.get("display_names")
    if isinstance(display_names, list):
        for name in display_names:
            if not isinstance(name, str):
                continue
            match = _DISPLAY_CIK.search(name)
            if match and int(match.group(1)) > 0:
                cik = match.group(1).zfill(10)
                ciks[cik] = _DISPLAY_CIK.sub("", name).strip()
    return tuple(FilingEntity(cik=cik, name=name) for cik, name in ciks.items())


def _associate_entities(
    response: EFTSSearchResponse, content: bytes
) -> list[EFTSHit]:
    """Attach raw source entity associations to the native parser's ordered hits."""
    payload = _JSON.validate_json(content)
    if not isinstance(payload, dict):
        raise ValueError("EFTS response must contain an object")
    hits_payload = payload.get("hits")
    if not isinstance(hits_payload, dict):
        raise ValueError("EFTS response must contain hits metadata")
    raw_hits = hits_payload.get("hits")
    if not isinstance(raw_hits, list) or len(raw_hits) != len(response.hits):
        raise ValueError("EFTS source and parsed result counts do not match")
    result: list[EFTSHit] = []
    for hit, raw in zip(response.hits, raw_hits, strict=True):
        source = raw.get("_source") if isinstance(raw, dict) else None
        entities = _source_entities(source) if isinstance(source, dict) else ()
        result.append(hit.model_copy(update={"entities": entities}))
    return result


@lru_cache(maxsize=1)
def _load_efts_module() -> ModuleType | None:
    """Load the optional native EFTS extension module."""
    try:
        return import_module("efts")
    except ImportError:  # pragma: no cover - depends on extension install
        logger.debug("efts import failed", exc_info=True)
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
        frozen=True,
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

        Uses bounded pages through the common SEC request layer.

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
        if max_results < 1:
            raise ValueError("max_results must be positive")
        hits: list[EFTSHit] = []
        offset = 0
        while len(hits) < max_results:
            response = await self.search(
                query,
                forms=forms,
                ciks=ciks,
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                limit=min(100, max_results - len(hits)),
                start=offset,
                sort_field=sort_field,
                sort_order=sort_order,
            )
            hits.extend(response.hits)
            if not response.hits or not response.has_more:
                break
            offset += len(response.hits)
        return hits[:max_results]

    async def batch_search(
        self,
        queries: Sequence[str],
        *,
        forms: Sequence[str] | None = None,
        ciks: Sequence[str] | None = None,
        tickers: Sequence[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit_per_query: int = 10,
        sort_field: EFTSSortField = EFTSSortField.relevance,
        sort_order: EFTSSortOrder = EFTSSortOrder.desc,
    ) -> list[EFTSBatchResult]:
        """Execute multiple search queries in a single batch.

        Returns one result or error per query under the shared request budget.

        Args:
            queries: List of search query strings
            forms: Optional form types to filter
            ciks: Optional CIK numbers to filter
            tickers: Optional ticker symbols to filter
            start_date: Optional start date for filing date range
            end_date: Optional end date for filing date range
            limit_per_query: Maximum results per query (1-100)
            sort_field: Field to sort by
            sort_order: Sort direction

        Returns:
            List of EFTSBatchResult, one per query in the same order
        """
        results: list[EFTSBatchResult] = []
        for query in queries:
            try:
                response = await self.search(
                    query,
                    forms=forms,
                    ciks=ciks,
                    tickers=tickers,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit_per_query,
                    sort_field=sort_field,
                    sort_order=sort_order,
                )
                results.append(
                    EFTSBatchResult(
                        query=query,
                        hits=response.hits,
                        total=response.total,
                    )
                )
            except (EFTSAPIError, ValueError) as exc:
                logger.debug("EFTS batch query failed", exc_info=True)
                results.append(EFTSBatchResult(query=query, error=str(exc)))
        return results

    async def _execute_search(
        self, params: EFTSSearchParams
    ) -> EFTSSearchResponse:
        """Fetch through the shared SEC transport and parse without native HTTP."""
        module = _load_efts_module()
        if module is None:
            raise EFTSAPIError(0, "Build EFTS parser with make build-ext")
        try:
            async with SecTransport(
                self.config.user_agent,
                timeout=self.config.timeout,
                retries=self.config.max_retries,
            ) as transport:
                content = await transport.get_bytes(
                    self.config.base_url,
                    params=params.to_api_params(),
                )
            parsed = module.parse_response_json(
                content.decode("utf-8"), params.query
            )
            response = EFTSSearchResponse.model_validate_json(parsed)
            return response.model_copy(
                update={
                    "start": params.start,
                    "limit": params.limit,
                    "hits": _associate_entities(response, content),
                }
            )
        except httpx.HTTPStatusError as exc:
            logger.debug("EFTS status failure", exc_info=True)
            raise EFTSAPIError(exc.response.status_code, str(exc)) from exc
        except (httpx.TransportError, ValueError, UnicodeError) as exc:
            logger.debug("EFTS request or parse failure", exc_info=True)
            raise EFTSAPIError(0, str(exc)) from exc


class EFTSAPIError(Exception):
    """Error from EFTS API request."""

    def __init__(
        self,
        status_code: int,
        message: str,
        detail: str | None = None,
    ) -> None:
        """Initialize EFTS wrapper with optional native backend and settings."""
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
