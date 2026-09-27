# src/market/__init__.pyi
"""Manual stub for the `market` native extension."""

from __future__ import annotations

from collections.abc import Awaitable, Iterable

class MarketSession:
    """Share a connection pool across cancellable, explicitly fresh requests."""

    def __init__(self) -> None:
        """Create a session without contacting Yahoo."""

    def retrieve_range_async(
        self, ticker: str, date_range: str
    ) -> Awaitable[list[dict[str, float | int]]]:
        """Fetch fresh quotes and propagate cancellation to the native request."""

    def wait_idle_async(self) -> Awaitable[None]:
        """Acknowledge completion or cancellation of active native requests."""

def fetch_price(ticker: str) -> float:
    """Fetch latest price for a single ticker (cached for 5 min)."""

def fetch_prices(tickers: Iterable[str]) -> dict[str, float]:
    """Fetch latest prices for multiple tickers (cached for 5 min)."""

def retrieve_range(
    ticker: str, date_range: str
) -> list[dict[str, float | int]]:
    """Fetch historical quotes for a date range (cached for 5 min).

    Args:
        ticker: Stock ticker symbol
        date_range: Date range as "YYYY-MM-DD..YYYY-MM-DD" or "YYYY-MM-DD,YYYY-MM-DD"
    """

def retrieve_ranges(
    tickers: Iterable[str], date_range: str
) -> dict[str, list[dict[str, float | int]]]:
    """Fetch historical quotes for multiple tickers over one date range."""

def clear_cache() -> None:
    """Clear all cached market data."""
