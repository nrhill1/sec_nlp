"""Tests for core stats event-study orchestration."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

import sec_nlp.core.stats.event_study as event_study_module
from sec_nlp.core.market import MarketQuote


class _FakeRetriever(event_study_module.MarketRangeRetriever):
    def __init__(self, quotes_by_ticker: dict[str, list[MarketQuote]]) -> None:
        self._quotes_by_ticker = quotes_by_ticker

    def retrieve_range(
        self, ticker: str, date_range: tuple[date, date]
    ) -> list[MarketQuote]:
        _ = date_range
        return list(self._quotes_by_ticker.get(ticker, []))


def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp())


def test_run_event_study_returns_normalized_metrics(monkeypatch) -> None:
    type _CallValue = tuple[list[float] | list[int] | int, ...] | list[float]
    calls: dict[str, _CallValue] = {}

    def fake_corr_event_study(
        prices: list[float],
        timestamps: list[int],
        event_timestamp: int,
        pre_window: int,
        post_window: int,
    ) -> SimpleNamespace:
        calls["event"] = (
            prices,
            timestamps,
            event_timestamp,
            pre_window,
            post_window,
        )
        return SimpleNamespace(
            car_pre=0.11,
            car_post=0.22,
            t_stat=1.5,
            p_value=0.03,
        )

    def fake_volume_spike(values: list[float]) -> float | None:
        calls["volume"] = values
        return 1.4

    monkeypatch.setattr(
        event_study_module, "corr_event_study", fake_corr_event_study
    )
    monkeypatch.setattr(
        event_study_module, "corr_volume_spike", fake_volume_spike
    )

    retriever = _FakeRetriever(
        {
            "ACME": [
                MarketQuote(_ts(2024, 1, 1), 10.0, 10.5, 9.5, 10.0, 100, 10.0),
                MarketQuote(_ts(2024, 1, 2), 11.0, 11.5, 10.5, 11.0, 120, 11.0),
                MarketQuote(_ts(2024, 1, 3), 13.0, 13.5, 12.5, 13.0, 80, 13.0),
                MarketQuote(_ts(2024, 1, 4), 12.0, 12.5, 11.5, 12.0, 140, 12.0),
            ],
            "SPY": [
                MarketQuote(_ts(2024, 1, 1), 5.0, 5.2, 4.8, 5.0, 1000, 5.0),
                MarketQuote(_ts(2024, 1, 2), 5.5, 5.7, 5.3, 5.5, 1100, 5.5),
                MarketQuote(_ts(2024, 1, 3), 6.5, 6.8, 6.3, 6.5, 900, 6.5),
                MarketQuote(_ts(2024, 1, 4), 6.0, 6.2, 5.8, 6.0, 950, 6.0),
            ],
        }
    )
    result = event_study_module.run_event_study(
        symbol="ACME",
        event_date="2024-01-02",
        benchmark="SPY",
        pre_window=1,
        post_window=2,
        retriever=retriever,
    )

    assert result.symbol == "ACME"
    assert result.event_date == "2024-01-02"
    assert result.car_pre == 0.11
    assert result.car_post == 0.22
    assert result.t_stat == 1.5
    assert result.p_value == 0.03
    assert result.volume_spike == 1.4

    assert calls["event"] == (
        [2.0, 2.0, 2.0, 2.0],
        [_ts(2024, 1, 1), _ts(2024, 1, 2), _ts(2024, 1, 3), _ts(2024, 1, 4)],
        _ts(2024, 1, 2),
        1,
        2,
    )
    assert calls["volume"] == [100.0, 120.0, 80.0, 140.0]


def test_run_event_study_requires_overlapping_quotes() -> None:
    retriever = _FakeRetriever(
        {
            "ACME": [
                MarketQuote(_ts(2024, 1, 1), 10.0, 10.5, 9.5, 10.0, 100, 10.0),
            ],
            "SPY": [
                MarketQuote(_ts(2024, 1, 2), 5.0, 5.2, 4.8, 5.0, 1000, 5.0),
            ],
        }
    )

    with pytest.raises(
        ValueError,
        match="insufficient overlapping market data",
    ):
        event_study_module.run_event_study(
            symbol="ACME",
            event_date="2024-01-02",
            benchmark="SPY",
            pre_window=1,
            post_window=1,
            retriever=retriever,
        )


def test_run_event_study_rejects_negative_windows() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        event_study_module.run_event_study(
            symbol="ACME",
            event_date="2024-01-02",
            pre_window=-1,
        )
