# src/sec_nlp/pipelines/presets/analyze/runnables/earnings_surprise.py
"""Earnings surprise runnable for EPS surprise and post-event CAR metrics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Protocol, runtime_checkable

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.market import (
    MarketQuote,
    create_market_retriever,
)
from sec_nlp.core.stats.correlation import (
    CorrExtensionError,
    car as corr_car,
)
from sec_nlp.types import JsonValue

EpsProvider = Callable[[str, str], tuple[float, date | str]]


@runtime_checkable
class RangeRetriever(Protocol):
    """Protocol for retrievers that can provide market ranges."""

    def retrieve_range(
        self,
        ticker: str,
        date_range: tuple[date, date],
    ) -> list[MarketQuote]: ...


class EarningsSurpriseInput(BaseModel):
    """Runnable input for earnings surprise calculations."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    symbol: str
    period: str
    expected_eps: float
    reported_eps: float | None = None
    event_date: str | None = None
    benchmark: str = Field(default="SPY", min_length=1)


class EarningsSurpriseOutput(BaseModel):
    """Runnable output for EPS surprise and post-earnings market response."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    symbol: str
    period: str
    reported_eps: float
    expected_eps: float
    surprise_pct: float
    post_earnings_car_1d: float
    post_earnings_car_5d: float


class EarningsSurpriseRunnable(
    RunnableSerializable[EarningsSurpriseInput, EarningsSurpriseOutput]
):
    """Compute EPS surprise percentage and 1-day/5-day post-earnings CAR."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    retriever: RangeRetriever | None = None
    eps_provider: EpsProvider | None = None

    def invoke(
        self,
        input: EarningsSurpriseInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> EarningsSurpriseOutput:
        _ = config
        _ = kwargs

        normalized_symbol = input.symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must be non-empty")
        if abs(input.expected_eps) < 1e-12:
            raise ValueError("expected_eps must be non-zero")

        reported_eps, event_day = self._resolve_eps_and_event_date(input)
        surprise_pct = (
            (reported_eps - input.expected_eps) / abs(input.expected_eps)
        ) * 100.0

        retriever = self.retriever or create_market_retriever()
        benchmark = input.benchmark.strip().upper()
        if not benchmark:
            raise ValueError("benchmark must be non-empty")

        post_car_1d = self._post_event_car(
            retriever=retriever,
            symbol=normalized_symbol,
            benchmark=benchmark,
            event_day=event_day,
            sessions=1,
        )
        post_car_5d = self._post_event_car(
            retriever=retriever,
            symbol=normalized_symbol,
            benchmark=benchmark,
            event_day=event_day,
            sessions=5,
        )

        return EarningsSurpriseOutput(
            symbol=normalized_symbol,
            period=input.period,
            reported_eps=reported_eps,
            expected_eps=input.expected_eps,
            surprise_pct=surprise_pct,
            post_earnings_car_1d=post_car_1d,
            post_earnings_car_5d=post_car_5d,
        )

    def _resolve_eps_and_event_date(
        self, input: EarningsSurpriseInput
    ) -> tuple[float, date]:
        """Resolve EPS metrics and event date for surprise analysis."""
        reported_eps = input.reported_eps
        event_day = (
            self._coerce_date(input.event_date)
            if input.event_date is not None
            else None
        )

        if self.eps_provider is not None:
            provider_eps, provider_event_day = self.eps_provider(
                input.symbol,
                input.period,
            )
            if reported_eps is None:
                reported_eps = float(provider_eps)
            if event_day is None:
                event_day = self._coerce_date(provider_event_day)

        if reported_eps is None:
            raise ValueError(
                "reported_eps is required when no eps_provider is configured"
            )
        if event_day is None:
            raise ValueError(
                "event_date is required when no eps_provider provides it"
            )

        return float(reported_eps), event_day

    @staticmethod
    def _coerce_date(value: date | str) -> date:
        """Coerce date-like values to date objects when possible."""
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)

    def _post_event_car(
        self,
        *,
        retriever: RangeRetriever,
        symbol: str,
        benchmark: str,
        event_day: date,
        sessions: int,
    ) -> float:
        """Compute post-event cumulative abnormal return window metrics."""
        window_end = event_day + timedelta(days=max(10, sessions * 3))
        symbol_quotes = retriever.retrieve_range(
            symbol, (event_day, window_end)
        )
        benchmark_quotes = retriever.retrieve_range(
            benchmark, (event_day, window_end)
        )

        symbol_closes, benchmark_closes = self._aligned_close_series(
            symbol_quotes, benchmark_quotes
        )
        required_points = sessions + 1
        if len(symbol_closes) < required_points:
            raise ValueError(
                f"insufficient market data for {sessions}-session CAR window"
            )

        symbol_window = symbol_closes[:required_points]
        benchmark_window = benchmark_closes[:required_points]

        try:
            computed_car = corr_car(symbol_window, benchmark_window)
        except CorrExtensionError:
            computed_car = self._fallback_car(symbol_window, benchmark_window)

        if computed_car is None:
            raise ValueError(f"unable to compute {sessions}-session CAR window")
        return float(computed_car)

    @staticmethod
    def _aligned_close_series(
        symbol_quotes: list[MarketQuote],
        benchmark_quotes: list[MarketQuote],
    ) -> tuple[list[float], list[float]]:
        """Build aligned close-price series for benchmark comparisons."""
        by_timestamp_symbol = {
            quote.timestamp: float(quote.close) for quote in symbol_quotes
        }
        by_timestamp_benchmark = {
            quote.timestamp: float(quote.close) for quote in benchmark_quotes
        }
        common_timestamps = sorted(
            set(by_timestamp_symbol) & set(by_timestamp_benchmark)
        )

        symbol_closes: list[float] = []
        benchmark_closes: list[float] = []
        for timestamp in common_timestamps:
            symbol_closes.append(by_timestamp_symbol[timestamp])
            benchmark_closes.append(by_timestamp_benchmark[timestamp])
        return symbol_closes, benchmark_closes

    @staticmethod
    def _fallback_car(
        symbol_closes: list[float],
        benchmark_closes: list[float],
    ) -> float | None:
        """Compute fallback CAR when event-study output is unavailable."""
        if len(symbol_closes) < 2 or len(benchmark_closes) < 2:
            return None
        first_symbol = symbol_closes[0]
        first_benchmark = benchmark_closes[0]
        if first_symbol == 0 or first_benchmark == 0:
            return None
        symbol_return = (symbol_closes[-1] / first_symbol) - 1.0
        benchmark_return = (benchmark_closes[-1] / first_benchmark) - 1.0
        return symbol_return - benchmark_return
