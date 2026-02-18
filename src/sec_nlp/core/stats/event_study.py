"""Event study orchestration built on top of the `corr` extension."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from sec_nlp.core.market import (
    MarketQuote,
    create_market_retriever,
)

from .correlation import (
    event_study as corr_event_study,
    volume_spike as corr_volume_spike,
)


class MarketRangeRetriever(Protocol):
    """Duck-typed market retriever dependency used by event-study helpers."""

    def retrieve_range(
        self,
        ticker: str,
        date_range: tuple[date, date],
    ) -> list[MarketQuote]: ...


class EventStudyResult(BaseModel):
    """Structured result for a single-symbol event study run."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    symbol: str
    event_date: str
    car_pre: float | None
    car_post: float | None
    t_stat: float | None
    p_value: float | None
    volume_spike: float | None


def _coerce_event_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _event_timestamp(event_date: date) -> int:
    return int(datetime.combine(event_date, time.min, tzinfo=UTC).timestamp())


def _align_price_ratio_series(
    symbol_quotes: list[MarketQuote],
    benchmark_quotes: list[MarketQuote],
) -> tuple[list[float], list[int], list[float]]:
    by_ts_symbol = {quote.timestamp: quote for quote in symbol_quotes}
    by_ts_benchmark = {quote.timestamp: quote for quote in benchmark_quotes}

    aligned_prices: list[float] = []
    aligned_timestamps: list[int] = []
    aligned_volumes: list[float] = []

    for ts in sorted(set(by_ts_symbol) & set(by_ts_benchmark)):
        symbol_quote = by_ts_symbol[ts]
        benchmark_quote = by_ts_benchmark[ts]
        if benchmark_quote.close == 0:
            continue
        aligned_timestamps.append(ts)
        aligned_prices.append(symbol_quote.close / benchmark_quote.close)
        aligned_volumes.append(float(symbol_quote.volume))

    return aligned_prices, aligned_timestamps, aligned_volumes


def run_event_study(
    symbol: str,
    event_date: str | date | datetime,
    benchmark: str = "SPY",
    pre_window: int = 5,
    post_window: int = 30,
    retriever: MarketRangeRetriever | None = None,
) -> EventStudyResult:
    """Run event-study metrics for a symbol using a benchmark-normalized series."""
    if pre_window < 0 or post_window < 0:
        raise ValueError("pre_window and post_window must be >= 0")

    event_day = _coerce_event_date(event_date)
    window_start = event_day - timedelta(days=pre_window)
    window_end = event_day + timedelta(days=post_window)

    retriever_instance = retriever or create_market_retriever()
    symbol_quotes = retriever_instance.retrieve_range(
        symbol,
        (window_start, window_end),
    )
    benchmark_quotes = retriever_instance.retrieve_range(
        benchmark,
        (window_start, window_end),
    )

    prices, timestamps, volumes = _align_price_ratio_series(
        symbol_quotes,
        benchmark_quotes,
    )
    if len(prices) < 2:
        raise ValueError("insufficient overlapping market data for event study")

    raw_result = corr_event_study(
        prices,
        timestamps,
        _event_timestamp(event_day),
        pre_window,
        post_window,
    )
    if raw_result is None:
        raw_result = SimpleNamespace(
            car_pre=None,
            car_post=None,
            t_stat=None,
            p_value=None,
        )

    return EventStudyResult(
        symbol=symbol,
        event_date=event_day.isoformat(),
        car_pre=raw_result.car_pre,
        car_post=raw_result.car_post,
        t_stat=raw_result.t_stat,
        p_value=raw_result.p_value,
        volume_spike=corr_volume_spike(volumes),
    )
