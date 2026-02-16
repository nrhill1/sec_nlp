"""Tests for analyze market correlation output helpers."""

from __future__ import annotations

from datetime import date
from typing import cast

from sec_nlp.pipelines.presets.analyze.io.formats import (
    market_correlation as formatter,
)
from sec_nlp.pipelines.presets.analyze.market import (
    MarketEnrichment,
    MarketGranularity,
    MarketQuoteSummary,
)
from sec_nlp.pipelines.types import AnalysisResultDict


def _build_market_data() -> MarketEnrichment:
    quotes = [
        MarketQuoteSummary(
            start_date=date(2024, 1, 5),
            end_date=date(2024, 1, 5),
            average_open=99.0,
            average_high=101.0,
            average_low=98.0,
            average_close=100.0,
            average_adjclose=100.0,
            average_volume=100.0,
        ),
        MarketQuoteSummary(
            start_date=date(2024, 1, 8),
            end_date=date(2024, 1, 8),
            average_open=101.0,
            average_high=103.0,
            average_low=100.0,
            average_close=102.0,
            average_adjclose=102.0,
            average_volume=110.0,
        ),
        MarketQuoteSummary(
            start_date=date(2024, 1, 9),
            end_date=date(2024, 1, 9),
            average_open=100.0,
            average_high=102.0,
            average_low=99.0,
            average_close=101.0,
            average_adjclose=101.0,
            average_volume=90.0,
        ),
        MarketQuoteSummary(
            start_date=date(2024, 1, 10),
            end_date=date(2024, 1, 10),
            average_open=102.0,
            average_high=104.0,
            average_low=101.0,
            average_close=103.0,
            average_adjclose=103.0,
            average_volume=150.0,
        ),
        MarketQuoteSummary(
            start_date=date(2024, 1, 11),
            end_date=date(2024, 1, 11),
            average_open=103.0,
            average_high=105.0,
            average_low=102.0,
            average_close=104.0,
            average_adjclose=104.0,
            average_volume=120.0,
        ),
        MarketQuoteSummary(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            average_open=105.0,
            average_high=107.0,
            average_low=104.0,
            average_close=106.0,
            average_adjclose=106.0,
            average_volume=130.0,
        ),
        MarketQuoteSummary(
            start_date=date(2024, 2, 9),
            end_date=date(2024, 2, 9),
            average_open=107.0,
            average_high=109.0,
            average_low=106.0,
            average_close=108.0,
            average_adjclose=108.0,
            average_volume=140.0,
        ),
    ]

    return MarketEnrichment(
        symbol="ACME",
        ticker="ACME",
        filing_date=date(2024, 1, 10),
        window_start=date(2024, 1, 1),
        window_end=date(2024, 2, 15),
        granularity=MarketGranularity.daily,
        quotes=quotes,
    )


def test_build_market_correlation_uses_stats_wrapper(
    monkeypatch,
) -> None:
    market_data = _build_market_data()
    results: list[AnalysisResultDict] = [
        {"sentiment": "positive"},
        {"sentiment": "negative"},
    ]

    calls: dict[str, list[list[float]]] = {
        "cumulative": [],
        "simple": [],
        "std": [],
        "volume": [],
    }

    pre_close = [100.0, 102.0, 101.0]
    post5_close = [103.0, 104.0, 106.0]
    post30_close = [103.0, 104.0, 106.0, 108.0]

    def fake_cumulative(prices: list[float]) -> float | None:
        calls["cumulative"].append(list(prices))
        if prices == pre_close:
            return 0.111
        if prices == post5_close:
            return 0.222
        if prices == post30_close:
            return 0.333
        return None

    def fake_simple(prices: list[float]) -> list[float]:
        calls["simple"].append(list(prices))
        if prices == pre_close:
            return [1.0, 2.0]
        if prices == post30_close:
            return [3.0, 4.0, 5.0]
        return []

    def fake_std_dev(values: list[float]) -> float:
        calls["std"].append(list(values))
        if values == [1.0, 2.0]:
            return 0.4
        if values == [3.0, 4.0, 5.0]:
            return 0.9
        return 0.0

    def fake_volume_spike(values: list[float]) -> float | None:
        calls["volume"].append(list(values))
        return 1.249

    monkeypatch.setattr(formatter, "corr_cumulative_return", fake_cumulative)
    monkeypatch.setattr(formatter, "corr_simple_returns", fake_simple)
    monkeypatch.setattr(formatter, "corr_std_dev", fake_std_dev)
    monkeypatch.setattr(formatter, "corr_volume_spike", fake_volume_spike)

    payload = formatter.build_market_correlation(market_data, results)

    assert payload is not None
    assert isinstance(payload, dict)
    metrics_raw = payload["metrics"]
    assert isinstance(metrics_raw, dict)
    metrics = cast(dict[str, float | None], metrics_raw)
    assert metrics["car_pre5"] == 0.11
    assert metrics["car_post5"] == 0.22
    assert metrics["car_post30"] == 0.33
    assert metrics["volatility_change"] == 0.5
    assert metrics["volume_spike"] == 1.25

    signal_raw = payload["signal_correlations"]
    assert isinstance(signal_raw, dict)
    signal = cast(dict[str, float | None], signal_raw)
    assert signal["sentiment_score"] == 0.0

    assert len(calls["cumulative"]) == 3
    assert len(calls["simple"]) == 2
    assert calls["std"] == [[1.0, 2.0], [3.0, 4.0, 5.0]]
    assert calls["volume"] == [[100.0, 110.0, 90.0, 150.0, 120.0, 130.0, 140.0]]


def test_build_market_correlation_falls_back_without_extension(
    monkeypatch,
) -> None:
    market_data = _build_market_data()
    results: list[AnalysisResultDict] = [
        {"sentiment": "positive"},
        {"sentiment": "negative"},
    ]

    def raise_corr_error(*_args, **_kwargs):
        raise formatter.CorrExtensionError("missing extension")

    monkeypatch.setattr(formatter, "corr_cumulative_return", raise_corr_error)
    monkeypatch.setattr(formatter, "corr_simple_returns", raise_corr_error)
    monkeypatch.setattr(formatter, "corr_std_dev", raise_corr_error)
    monkeypatch.setattr(formatter, "corr_volume_spike", raise_corr_error)

    payload = formatter.build_market_correlation(market_data, results)

    assert payload is not None
    assert isinstance(payload, dict)
    metrics_raw = payload["metrics"]
    assert isinstance(metrics_raw, dict)
    metrics = cast(dict[str, float | None], metrics_raw)
    assert metrics["car_pre5"] == 0.01
    assert metrics["car_post5"] == 0.03
    assert metrics["car_post30"] == 0.05
    assert metrics["volatility_change"] == -0.01
    assert metrics["volume_spike"] == 1.25
