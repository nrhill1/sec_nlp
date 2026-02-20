"""Tests for derived market analytics service."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pytest

from sec_nlp.core.market import MarketQuote
from sec_nlp.core.market_analytics import build_market_context


class _FakeRetriever:
    def __init__(self, by_symbol: dict[str, list[MarketQuote]]) -> None:
        self.by_symbol = by_symbol

    def retrieve_ranges(
        self,
        tickers: Sequence[str],
        date_range: tuple[date, date],
    ) -> dict[str, list[MarketQuote]]:
        return {
            ticker: list(self.by_symbol.get(ticker, [])) for ticker in tickers
        }

    def retrieve_range(
        self,
        ticker: str,
        date_range: tuple[date, date],
    ) -> list[MarketQuote]:
        return list(self.by_symbol.get(ticker, []))


def _quote(
    ts: int,
    close: float,
    *,
    high: float | None = None,
    low: float | None = None,
    volume: int = 1000,
) -> MarketQuote:
    return MarketQuote(
        timestamp=ts,
        open_price=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
        adjclose=close,
    )


def test_build_market_context_computes_core_metrics() -> None:
    retriever = _FakeRetriever(
        {
            "AAA": [
                _quote(1, 100.0, high=102.0, low=98.0),
                _quote(2, 110.0, high=113.0, low=108.0),
                _quote(3, 99.0, high=101.0, low=95.0),
            ],
            "SPY": [
                _quote(1, 100.0, high=101.0, low=99.0),
                _quote(2, 110.0, high=111.0, low=109.0),
                _quote(3, 121.0, high=122.0, low=120.0),
            ],
        }
    )

    bundle = build_market_context(
        symbols=["AAA"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        benchmark="SPY",
        retriever=retriever,
    )

    assert bundle.window == "2024-01-01..2024-01-31"
    assert bundle.benchmark == "SPY"
    assert bundle.symbols == ["AAA"]
    assert len(bundle.metrics) == 1
    metric = bundle.metrics[0]
    assert metric.symbol == "AAA"
    assert metric.return_pct is not None
    assert metric.benchmark_return_pct is not None
    assert metric.spread_pct is not None
    assert metric.max_drawdown is not None
    assert metric.observations == 3
    assert metric.return_pct == pytest.approx(-1.0, abs=1e-6)
    assert metric.benchmark_return_pct == pytest.approx(21.0, abs=1e-6)
    assert metric.spread_pct == pytest.approx(-22.0, abs=1e-6)
    assert metric.max_drawdown == pytest.approx(10.0, abs=1e-6)


def test_build_market_context_handles_short_or_missing_series() -> None:
    retriever = _FakeRetriever(
        {
            "AAA": [_quote(1, 100.0)],
            "SPY": [_quote(1, 100.0)],
        }
    )
    bundle = build_market_context(
        symbols=["AAA"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        benchmark="SPY",
        retriever=retriever,
    )

    metric = bundle.metrics[0]
    assert metric.return_pct is None
    assert metric.benchmark_return_pct is None
    assert metric.spread_pct is None
    assert metric.beta is None
    assert metric.std_dev is None
    assert metric.atr is None
    assert metric.max_drawdown is None
    assert metric.volume_spike is None
    assert metric.observations == 1


def test_build_market_context_validates_date_range() -> None:
    with pytest.raises(ValueError, match="start_date must be <="):
        build_market_context(
            symbols=["AAA"],
            start_date=date(2024, 2, 1),
            end_date=date(2024, 1, 1),
        )


def test_build_market_context_handles_empty_symbols() -> None:
    bundle = build_market_context(
        symbols=[],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )
    assert bundle.symbols == []
    assert bundle.metrics == []
