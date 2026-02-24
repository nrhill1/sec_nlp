# src/sec_nlp/pipelines/presets/analyze/io/formats/market_correlation.py
"""Market correlation output formatting helpers."""

from __future__ import annotations

from datetime import date, timedelta

from sec_nlp.core.stats.correlation import (
    CorrExtensionError,
    cumulative_return as corr_cumulative_return,
    simple_returns as corr_simple_returns,
    std_dev as corr_std_dev,
    volume_spike as corr_volume_spike,
)
from sec_nlp.pipelines.serialization import round_score
from sec_nlp.pipelines.types import AnalysisResultDict
from sec_nlp.types import JsonDict

from ...market import MarketEnrichment, MarketQuoteSummary


def _select_quotes_for_window(
    quotes: list[MarketQuoteSummary],
    *,
    start: date,
    end: date,
) -> list[MarketQuoteSummary]:
    return [
        quote
        for quote in quotes
        if quote.start_date <= end and quote.end_date >= start
    ]


def _compute_cumulative_return(
    quotes: list[MarketQuoteSummary],
) -> float | None:
    closes = [quote.average_close for quote in quotes]
    if len(closes) < 2:
        return None
    try:
        return corr_cumulative_return(closes)
    except CorrExtensionError:
        first = closes[0]
        if first == 0:
            return None
        return (closes[-1] / first) - 1.0


def _compute_returns(
    quotes: list[MarketQuoteSummary],
) -> list[float]:
    closes = [quote.average_close for quote in quotes]
    if len(closes) < 2:
        return []
    try:
        return corr_simple_returns(closes)
    except CorrExtensionError:
        returns: list[float] = []
        for prev, curr in zip(closes, closes[1:], strict=False):
            if prev == 0:
                continue
            returns.append((curr / prev) - 1.0)
        return returns


def _compute_volatility(
    returns: list[float],
) -> float | None:
    if len(returns) < 2:
        return None
    try:
        return corr_std_dev(returns)
    except CorrExtensionError:
        avg = sum(returns) / len(returns)
        variance = sum((value - avg) ** 2 for value in returns) / len(returns)
        return variance**0.5


def _compute_volume_spike(
    quotes: list[MarketQuoteSummary],
) -> float | None:
    volumes = [quote.average_volume for quote in quotes]
    if not volumes:
        return None
    try:
        return corr_volume_spike(volumes)
    except CorrExtensionError:
        avg_volume = sum(volumes) / len(volumes)
        if avg_volume == 0:
            return None
        return max(volumes) / avg_volume


def _compute_net_sentiment(
    results: list[AnalysisResultDict],
) -> float | None:
    if not results:
        return None
    score_map = {
        "positive": 1.0,
        "neutral": 0.0,
        "negative": -1.0,
    }
    scores: list[float] = []
    for result in results:
        sentiment = result.get("sentiment")
        if isinstance(sentiment, str):
            cleaned = sentiment.strip().lower()
            score = score_map.get(cleaned)
            if score is not None:
                scores.append(score)
    if not scores:
        return None
    return sum(scores) / len(scores)


def build_market_correlation(
    market_data: MarketEnrichment | None,
    results: list[AnalysisResultDict],
) -> JsonDict | None:
    if market_data is None or not market_data.quotes:
        return None

    quotes = sorted(
        market_data.quotes, key=lambda q: (q.start_date, q.end_date)
    )
    filing_date = market_data.filing_date
    event_window = [-5, 30]
    if filing_date is None:
        metrics: JsonDict = {
            "car_pre5": None,
            "car_post5": None,
            "car_post30": None,
            "volume_spike": None,
            "volatility_change": None,
        }
    else:
        pre_start = filing_date + timedelta(days=event_window[0])
        pre_end = filing_date - timedelta(days=1)
        post5_end = filing_date + timedelta(days=5)
        post30_end = filing_date + timedelta(days=event_window[1])

        pre_quotes = _select_quotes_for_window(
            quotes, start=pre_start, end=pre_end
        )
        post5_quotes = _select_quotes_for_window(
            quotes, start=filing_date, end=post5_end
        )
        post30_quotes = _select_quotes_for_window(
            quotes, start=filing_date, end=post30_end
        )

        pre_returns = _compute_returns(pre_quotes)
        post_returns = _compute_returns(post30_quotes)
        pre_volatility = _compute_volatility(pre_returns)
        post_volatility = _compute_volatility(post_returns)
        volatility_change = (
            (post_volatility - pre_volatility)
            if post_volatility is not None and pre_volatility is not None
            else None
        )

        window_quotes = _select_quotes_for_window(
            quotes, start=pre_start, end=post30_end
        )

        metrics = {
            "car_pre5": _compute_cumulative_return(pre_quotes),
            "car_post5": _compute_cumulative_return(post5_quotes),
            "car_post30": _compute_cumulative_return(post30_quotes),
            "volume_spike": _compute_volume_spike(window_quotes),
            "volatility_change": volatility_change,
        }

    signal_correlations: JsonDict = {
        "sentiment_score": _compute_net_sentiment(results),
        "risk_novelty_count": None,
        "warranty_accrual_delta": None,
    }

    def _round_value(value: float | None) -> float | None:
        return round_score(value)

    metrics = {
        key: _round_value(value)
        if isinstance(value, (int, float)) or value is None
        else value
        for key, value in metrics.items()
    }
    signal_correlations = {
        key: _round_value(value)
        if isinstance(value, (int, float)) or value is None
        else value
        for key, value in signal_correlations.items()
    }

    return {
        "filing_date": filing_date.isoformat() if filing_date else None,
        "event_window": event_window,
        "metrics": metrics,
        "signal_correlations": signal_correlations,
    }
