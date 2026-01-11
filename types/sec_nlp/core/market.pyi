"""Manual stub for the market helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from types import ModuleType

class MarketExtensionError(RuntimeError): ...

class MarketQuote:
    timestamp: int
    open_price: float
    high: float
    low: float
    close: float
    volume: int
    adjclose: float

class MarketCacheEntry:
    expires_at: float
    quotes: tuple[MarketQuote, ...]

def _load_market_module() -> ModuleType: ...
def _coerce_date(value: date | datetime) -> date: ...
def _coerce_date_range(
    date_range: Sequence[date | datetime],
) -> tuple[date, date]: ...

class MarketRetriever:
    def __init__(
        self,
        module: ModuleType | None = ...,
        *,
        cache_ttl_seconds: float | None = ...,
        cache_max_entries: int | None = ...,
        retry_attempts: int | None = ...,
        retry_backoff_seconds: float | None = ...,
        retry_backoff_multiplier: float | None = ...,
    ) -> None: ...
    def fetch_price(self, ticker: str) -> float: ...
    def retrieve_range(
        self, ticker: str, date_range: Sequence[date | datetime]
    ) -> list[MarketQuote]: ...

def create_market_retriever() -> MarketRetriever: ...
