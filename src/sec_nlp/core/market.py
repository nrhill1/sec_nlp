"""Market data retrieval helpers backed by the Rust `market` extension."""

from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from importlib import import_module
from time import monotonic, sleep
from types import ModuleType
from typing import TypeVar

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.settings import (
    MARKET_CACHE_MAX_ENTRIES,
    MARKET_CACHE_TTL_SECONDS,
    MARKET_RETRY_ATTEMPTS,
    MARKET_RETRY_BACKOFF_MULTIPLIER,
    MARKET_RETRY_BACKOFF_SECONDS,
)

CacheKey = tuple[str, str]
T = TypeVar("T")


class MarketExtensionError(RuntimeError):
    """Raised when the Rust `market` extension is unavailable."""


@dataclass(frozen=True)
class MarketQuote:
    """Market quote data returned by the Rust extension."""

    timestamp: int
    open_price: float
    high: float
    low: float
    close: float
    volume: int
    adjclose: float


@dataclass(frozen=True)
class MarketCacheEntry:
    """In-memory cache entry for market quotes."""

    expires_at: float
    quotes: tuple[MarketQuote, ...]


def _load_market_module() -> ModuleType:
    try:
        return import_module("market")
    except Exception as exc:  # pragma: no cover - depends on extension install
        raise MarketExtensionError(
            "market extension is not available; build it with "
            "`make maturin-dev` or `make market-dev`."
        ) from exc


def _coerce_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("date_range values must be date or datetime")


def _coerce_date_range(
    date_range: Sequence[date | datetime],
) -> tuple[date, date]:
    if len(date_range) != 2:
        raise ValueError("date_range must contain exactly two values")
    start_date = _coerce_date(date_range[0])
    end_date = _coerce_date(date_range[1])
    if start_date > end_date:
        raise ValueError("date_range end must be >= start")
    return start_date, end_date


def _normalize_quote(raw: dict[str, float | int]) -> MarketQuote:
    return MarketQuote(
        timestamp=int(raw["timestamp"]),
        open_price=float(raw["open_price"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        volume=int(raw["volume"]),
        adjclose=float(raw["adjclose"]),
    )


class MarketRetriever:
    """Small retrieval helper for Yahoo-backed market data."""

    def __init__(
        self,
        module: ModuleType | None = None,
        *,
        cache_ttl_seconds: float | None = None,
        cache_max_entries: int | None = None,
        retry_attempts: int | None = None,
        retry_backoff_seconds: float | None = None,
        retry_backoff_multiplier: float | None = None,
    ) -> None:
        self._market = module or _load_market_module()
        self._cache_ttl_seconds = (
            MARKET_CACHE_TTL_SECONDS
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        self._cache_max_entries = (
            MARKET_CACHE_MAX_ENTRIES
            if cache_max_entries is None
            else cache_max_entries
        )
        self._retry_attempts = (
            MARKET_RETRY_ATTEMPTS if retry_attempts is None else retry_attempts
        )
        self._retry_backoff_seconds = (
            MARKET_RETRY_BACKOFF_SECONDS
            if retry_backoff_seconds is None
            else retry_backoff_seconds
        )
        self._retry_backoff_multiplier = (
            MARKET_RETRY_BACKOFF_MULTIPLIER
            if retry_backoff_multiplier is None
            else retry_backoff_multiplier
        )
        self._cache: OrderedDict[CacheKey, MarketCacheEntry] = OrderedDict()

    def _log(self, message: str, *args: str) -> None:
        logger.debug(message, *args)

    def _log(self, message: str, *args: object) -> None:
        logger.debug(message, *args)

    def _cache_enabled(self) -> bool:
        return self._cache_ttl_seconds > 0 and self._cache_max_entries > 0

    def _get_cached_quotes(
        self,
        cache_key: CacheKey,
        now: float,
    ) -> tuple[MarketQuote, ...] | None:
        if not self._cache_enabled():
            return None
        entry = self._cache.get(cache_key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            self._cache.pop(cache_key, None)
            return None
        self._cache.move_to_end(cache_key)
        return entry.quotes

    def _set_cached_quotes(
        self,
        cache_key: CacheKey,
        now: float,
        quotes: tuple[MarketQuote, ...],
    ) -> None:
        if not self._cache_enabled():
            return
        self._cache[cache_key] = MarketCacheEntry(
            expires_at=now + self._cache_ttl_seconds,
            quotes=quotes,
        )
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self._cache_max_entries:
            self._cache.popitem(last=False)

    def _call_with_retry(
        self,
        operation_name: str,
        operation: Callable[[], T],
    ) -> T:
        attempt = 0
        delay_seconds = self._retry_backoff_seconds
        while True:
            try:
                return operation()
            except MarketExtensionError:
                raise
            except Exception as exc:
                attempt += 1
                if attempt >= self._retry_attempts:
                    raise MarketExtensionError(
                        f"{operation_name} failed after {attempt} attempts"
                    ) from exc
                sleep(delay_seconds)
                delay_seconds *= self._retry_backoff_multiplier

    def fetch_price(self, ticker: str) -> float:
        """Fetch the latest close price for a ticker."""

        def _fetch() -> float:
            return self._market.fetch_price(ticker)

        self._log("fetch_price ticker=%s", ticker)
        return self._call_with_retry("fetch_price", _fetch)

    def fetch_prices(self, tickers: Sequence[str]) -> dict[str, float]:
        """Fetch latest close prices for multiple tickers."""
        normalized = tuple(
            ticker.strip().upper() for ticker in tickers if ticker.strip()
        )
        if not normalized:
            return {}

        def _fetch() -> dict[str, float]:
            return self._market.fetch_prices(list(normalized))

        self._log("fetch_prices tickers=%s", ", ".join(normalized))
        return self._call_with_retry("fetch_prices", _fetch)

    def retrieve_range(
        self,
        ticker: str,
        date_range: Sequence[date | datetime],
    ) -> list[MarketQuote]:
        """Fetch OHLCV quotes for a ticker within a date range.

        Expects a (start_date, end_date) sequence of date/datetime values.
        """
        start_date, end_date = _coerce_date_range(date_range)
        date_range_text = f"{start_date.isoformat()}..{end_date.isoformat()}"
        cache_key = (ticker, date_range_text)
        now = monotonic()
        cached_quotes = self._get_cached_quotes(cache_key, now)
        if cached_quotes is not None:
            return list(cached_quotes)

        def _fetch() -> list[dict[str, float | int]]:
            return self._market.retrieve_range(ticker, date_range_text)

        self._log("retrieve_range ticker=%s range=%s", ticker, date_range_text)
        raw_quotes = self._call_with_retry("retrieve_range", _fetch)
        quotes = [_normalize_quote(raw_quote) for raw_quote in raw_quotes]
        self._set_cached_quotes(cache_key, now, tuple(quotes))
        return quotes

    def retrieve_ranges(
        self,
        tickers: Sequence[str],
        date_range: Sequence[date | datetime],
    ) -> dict[str, list[MarketQuote]]:
        """Fetch OHLCV quotes for multiple tickers within a date range."""
        normalized = [
            ticker.strip().upper() for ticker in tickers if ticker.strip()
        ]
        if not normalized:
            return {}

        start_date, end_date = _coerce_date_range(date_range)
        date_range_text = f"{start_date.isoformat()}..{end_date.isoformat()}"
        now = monotonic()

        output: dict[str, list[MarketQuote]] = {}
        missing: list[str] = []
        for ticker in normalized:
            cached = self._get_cached_quotes((ticker, date_range_text), now)
            if cached is not None:
                output[ticker] = list(cached)
            else:
                missing.append(ticker)

        if missing:
            self._log(
                "retrieve_ranges tickers=%s range=%s",
                ", ".join(missing),
                date_range_text,
            )
            fetch_batch = getattr(self._market, "retrieve_ranges", None)
            if callable(fetch_batch):
                raw_batch = self._call_with_retry(
                    "retrieve_ranges",
                    lambda: fetch_batch(missing, date_range_text),
                )
                for ticker, raw_quotes in dict(raw_batch).items():
                    quotes = [
                        _normalize_quote(raw_quote) for raw_quote in raw_quotes
                    ]
                    output[str(ticker)] = quotes
                    self._set_cached_quotes(
                        (str(ticker), date_range_text),
                        now,
                        tuple(quotes),
                    )
            else:
                for ticker in missing:
                    output[ticker] = self.retrieve_range(
                        ticker, (start_date, end_date)
                    )

        ordered: dict[str, list[MarketQuote]] = {}
        for ticker in normalized:
            quotes = output.get(ticker)
            if quotes is not None:
                ordered[ticker] = quotes
        return ordered


def create_market_retriever() -> MarketRetriever:
    """Create a MarketRetriever instance."""
    return MarketRetriever()
