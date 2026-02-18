"""Tests for economic indicator integration helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from sec_nlp.core.edgar import economic
from sec_nlp.core.market import MarketQuote


def _quote(day_offset: int, close: float) -> MarketQuote:
    timestamp = int(
        datetime(2024, 1, 1, tzinfo=UTC).timestamp() + day_offset * 86_400
    )
    return MarketQuote(
        timestamp=timestamp,
        open_price=close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
        adjclose=close,
    )


def test_fetch_series_normalizes_fred_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeFred:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        def get_series(
            self,
            series_id: str,
            **kwargs: str,
        ) -> dict[date | str, float | str]:
            assert series_id == "UNRATE"
            assert kwargs["observation_start"] == "2024-01-01"
            assert kwargs["observation_end"] == "2024-12-31"
            return {
                date(2024, 1, 1): 3.7,
                "2024-02-01": float("nan"),
                "2024-03-01": "3.9",
            }

        def get_series_info(self, _series_id: str) -> SimpleNamespace:
            return SimpleNamespace(title="Unemployment Rate")

    monkeypatch.setattr(
        economic,
        "_load_fred_module",
        lambda: SimpleNamespace(Fred=_FakeFred),
    )
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    series = economic.fetch_series(
        "unrate", start_date="2024-01-01", end_date="2024-12-31"
    )

    assert series.series_id == "UNRATE"
    assert series.description == "Unemployment Rate"
    assert series.observations == [("2024-01-01", 3.7), ("2024-03-01", 3.9)]


def test_align_to_filings_picks_nearest_observation() -> None:
    series = economic.EconomicSeries(
        series_id="UNRATE",
        description="Unemployment Rate",
        observations=[
            ("2024-03-01", 3.9),
            ("2024-01-01", 3.7),
            ("2024-02-01", 3.8),
        ],
    )

    contexts = economic.align_to_filings(
        series,
        ["2024-01-15", "2024-02-28", "2024-03-20"],
    )

    assert [context.filing_date for context in contexts] == [
        "2024-01-15",
        "2024-02-28",
        "2024-03-20",
    ]
    assert [context.unemployment_rate for context in contexts] == [
        3.7,
        3.9,
        3.9,
    ]


def test_compute_macro_sensitivity_uses_corr_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRetriever:
        def retrieve_range(
            self,
            ticker: str,
            date_range: tuple[date, date],
        ) -> list[MarketQuote]:
            _ = ticker
            _ = date_range
            return [
                _quote(0, 100.0),
                _quote(1, 101.0),
                _quote(2, 103.0),
                _quote(3, 106.0),
            ]

    monkeypatch.setattr(
        economic,
        "fetch_series",
        lambda *_args, **_kwargs: economic.EconomicSeries(
            series_id="UNRATE",
            description="Unemployment Rate",
            observations=[
                ("2024-01-02", 3.7),
                ("2024-01-03", 3.8),
                ("2024-01-04", 3.9),
            ],
        ),
    )
    monkeypatch.setattr(economic, "corr_pearson", lambda _x, _y: 0.75)

    result = economic.compute_macro_sensitivity(
        symbol="abc",
        indicator_id="unrate",
        window_days=3,
        retriever=_FakeRetriever(),
    )

    assert result.symbol == "ABC"
    assert result.indicator_id == "UNRATE"
    assert result.window_days == 3
    assert result.correlation == pytest.approx(0.75)
    assert 0.0 <= result.p_value <= 1.0


def test_compute_macro_sensitivity_falls_back_on_corr_extension_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeRetriever:
        def retrieve_range(
            self,
            ticker: str,
            date_range: tuple[date, date],
        ) -> list[MarketQuote]:
            _ = ticker
            _ = date_range
            return [
                _quote(0, 100.0),
                _quote(1, 110.0),  # +10%
                _quote(2, 132.0),  # +20%
                _quote(3, 171.6),  # +30%
            ]

    monkeypatch.setattr(
        economic,
        "fetch_series",
        lambda *_args, **_kwargs: economic.EconomicSeries(
            series_id="UNRATE",
            description="Unemployment Rate",
            observations=[
                ("2024-01-02", 1.0),
                ("2024-01-03", 2.0),
                ("2024-01-04", 3.0),
            ],
        ),
    )

    def _raise_corr_error(_x: list[float], _y: list[float]) -> float:
        raise economic.CorrExtensionError("corr unavailable")

    monkeypatch.setattr(economic, "corr_pearson", _raise_corr_error)

    result = economic.compute_macro_sensitivity(
        symbol="ABC",
        indicator_id="UNRATE",
        window_days=3,
        retriever=_FakeRetriever(),
    )

    assert result.correlation == pytest.approx(1.0)
