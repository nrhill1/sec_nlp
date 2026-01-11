"""Manual stub for the `market` native extension."""

from __future__ import annotations

from collections.abc import Iterable

def fetch_price(ticker: str) -> float: ...
def fetch_prices(tickers: Iterable[str]) -> dict[str, float]: ...
def retrieve_range(
    ticker: str, date_range: str
) -> list[dict[str, float | int]]: ...
