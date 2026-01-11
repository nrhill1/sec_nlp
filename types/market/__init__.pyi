"""Manual stub for the `market` native extension."""

from __future__ import annotations

from collections.abc import Iterable

def fetch_price(ticker: str) -> float:
    """Fetch latest price for a single ticker (cached for 5 min)."""
    ...

def fetch_prices(tickers: Iterable[str]) -> dict[str, float]:
    """Fetch latest prices for multiple tickers (cached for 5 min)."""
    ...

def retrieve_range(
    ticker: str, date_range: str
) -> list[dict[str, float | int]]:
    """Fetch historical quotes for a date range (cached for 5 min).

    Args:
        ticker: Stock ticker symbol
        date_range: Date range as "YYYY-MM-DD..YYYY-MM-DD" or "YYYY-MM-DD,YYYY-MM-DD"
    """
    ...

def clear_cache() -> None:
    """Clear all cached market data."""
    ...
