"""Derived market analytics for chat/retrieve context enrichment."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.market import (
    MarketQuote,
    create_market_retriever,
)
from sec_nlp.core.stats import (
    CorrExtensionError,
    average_true_range,
    beta,
    simple_returns,
    std_dev,
    volume_spike,
)


class _BatchMarketRetriever(Protocol):
    """Duck-typed retriever dependency for analytics tests/composition."""

    def retrieve_range(
        self,
        ticker: str,
        date_range: tuple[date, date],
    ) -> list[MarketQuote]: ...

    def retrieve_ranges(
        self,
        tickers: Sequence[str],
        date_range: tuple[date, date],
    ) -> dict[str, list[MarketQuote]]: ...


class MarketContextMetric(BaseModel):
    """Per-symbol derived market metrics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    return_pct: float | None = None
    benchmark_return_pct: float | None = None
    spread_pct: float | None = None
    beta: float | None = None
    std_dev: float | None = None
    atr: float | None = None
    max_drawdown: float | None = None
    volume_spike: float | None = None
    observations: int = 0


class MarketContextBundle(BaseModel):
    """Aggregate market context payload across symbols."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window: str
    benchmark: str
    symbols: list[str] = Field(default_factory=list)
    metrics: list[MarketContextMetric] = Field(default_factory=list)


def _normalize_symbols(symbols: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = raw.strip().upper()
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


def _sorted_quotes(quotes: Sequence[MarketQuote]) -> list[MarketQuote]:
    return sorted(quotes, key=lambda quote: quote.timestamp)


def _close_series(quotes: Sequence[MarketQuote]) -> list[float]:
    ordered = _sorted_quotes(quotes)
    closes: list[float] = []
    for quote in ordered:
        closes.append(quote.adjclose if quote.adjclose > 0 else quote.close)
    return closes


def _return_pct(closes: Sequence[float]) -> float | None:
    if len(closes) < 2:
        return None
    first = closes[0]
    last = closes[-1]
    if first <= 0:
        return None
    return ((last / first) - 1.0) * 100.0


def _safe_simple_returns(closes: Sequence[float]) -> list[float]:
    if len(closes) < 2:
        return []
    try:
        return simple_returns(closes)
    except (CorrExtensionError, ValueError):
        output: list[float] = []
        for prev_close, close in zip(closes, closes[1:], strict=False):
            if prev_close == 0:
                continue
            output.append((close / prev_close) - 1.0)
        return output


def _returns_by_timestamp(
    quotes: Sequence[MarketQuote],
) -> dict[int, float]:
    ordered = _sorted_quotes(quotes)
    closes = _close_series(ordered)
    returns = _safe_simple_returns(closes)
    return {
        int(ordered[idx + 1].timestamp): value
        for idx, value in enumerate(returns)
    }


def _aligned_returns(
    symbol_quotes: Sequence[MarketQuote],
    benchmark_quotes: Sequence[MarketQuote],
) -> tuple[list[float], list[float]]:
    symbol_returns = _returns_by_timestamp(symbol_quotes)
    benchmark_returns = _returns_by_timestamp(benchmark_quotes)
    common_timestamps = sorted(set(symbol_returns) & set(benchmark_returns))
    if not common_timestamps:
        return [], []
    symbol = [symbol_returns[timestamp] for timestamp in common_timestamps]
    benchmark = [
        benchmark_returns[timestamp] for timestamp in common_timestamps
    ]
    return symbol, benchmark


def _safe_beta(
    symbol_quotes: Sequence[MarketQuote],
    benchmark_quotes: Sequence[MarketQuote],
) -> float | None:
    symbol_returns, benchmark_returns = _aligned_returns(
        symbol_quotes, benchmark_quotes
    )
    if len(symbol_returns) < 2 or len(benchmark_returns) < 2:
        return None
    try:
        return beta(symbol_returns, benchmark_returns)
    except (CorrExtensionError, ValueError):
        return None


def _safe_std_dev(closes: Sequence[float]) -> float | None:
    returns = _safe_simple_returns(closes)
    if len(returns) < 2:
        return None
    try:
        return std_dev(returns)
    except (CorrExtensionError, ValueError):
        return None


def _safe_atr(quotes: Sequence[MarketQuote]) -> float | None:
    ordered = _sorted_quotes(quotes)
    if len(ordered) < 2:
        return None
    highs = [quote.high for quote in ordered]
    lows = [quote.low for quote in ordered]
    closes = [quote.close for quote in ordered]
    try:
        return average_true_range(highs, lows, closes)
    except (CorrExtensionError, ValueError):
        return None


def _safe_volume_spike(quotes: Sequence[MarketQuote]) -> float | None:
    ordered = _sorted_quotes(quotes)
    volumes = [float(quote.volume) for quote in ordered]
    if len(volumes) < 2:
        return None
    try:
        return volume_spike(volumes)
    except (CorrExtensionError, ValueError):
        return None


def _max_drawdown_pct(closes: Sequence[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    if peak <= 0:
        return None
    max_drawdown = 0.0
    for close in closes[1:]:
        if close > peak:
            peak = close
            continue
        if peak <= 0:
            continue
        drawdown = (1.0 - (close / peak)) * 100.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def _resolve_quotes(
    retriever: _BatchMarketRetriever,
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> dict[str, list[MarketQuote]]:
    if hasattr(retriever, "retrieve_ranges"):
        batch = retriever.retrieve_ranges(symbols, (start_date, end_date))
        return {symbol.upper(): quotes for symbol, quotes in batch.items()}

    output: dict[str, list[MarketQuote]] = {}
    for symbol in symbols:
        output[symbol] = retriever.retrieve_range(
            symbol, (start_date, end_date)
        )
    return output


def build_market_context(
    symbols: Sequence[str],
    start_date: date,
    end_date: date,
    benchmark: str = "SPY",
    retriever: _BatchMarketRetriever | None = None,
) -> MarketContextBundle:
    """Build market context metrics for symbols vs. a benchmark."""
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")

    normalized_symbols = _normalize_symbols(symbols)
    benchmark_symbol = benchmark.strip().upper()
    if not benchmark_symbol:
        raise ValueError("benchmark cannot be empty")

    if not normalized_symbols:
        return MarketContextBundle(
            window=f"{start_date.isoformat()}..{end_date.isoformat()}",
            benchmark=benchmark_symbol,
            symbols=[],
            metrics=[],
        )

    retriever_instance = retriever or create_market_retriever()
    query_symbols = list(normalized_symbols)
    if benchmark_symbol not in query_symbols:
        query_symbols.append(benchmark_symbol)

    quotes_by_symbol = _resolve_quotes(
        retriever=retriever_instance,
        symbols=query_symbols,
        start_date=start_date,
        end_date=end_date,
    )
    benchmark_quotes = quotes_by_symbol.get(benchmark_symbol, [])
    benchmark_return_pct = _return_pct(_close_series(benchmark_quotes))

    metrics: list[MarketContextMetric] = []
    for symbol in normalized_symbols:
        symbol_quotes = quotes_by_symbol.get(symbol, [])
        closes = _close_series(symbol_quotes)
        return_pct = _return_pct(closes)
        spread_pct = None
        if return_pct is not None and benchmark_return_pct is not None:
            spread_pct = return_pct - benchmark_return_pct

        metrics.append(
            MarketContextMetric(
                symbol=symbol,
                return_pct=return_pct,
                benchmark_return_pct=benchmark_return_pct,
                spread_pct=spread_pct,
                beta=_safe_beta(symbol_quotes, benchmark_quotes),
                std_dev=_safe_std_dev(closes),
                atr=_safe_atr(symbol_quotes),
                max_drawdown=_max_drawdown_pct(closes),
                volume_spike=_safe_volume_spike(symbol_quotes),
                observations=len(symbol_quotes),
            )
        )

    return MarketContextBundle(
        window=f"{start_date.isoformat()}..{end_date.isoformat()}",
        benchmark=benchmark_symbol,
        symbols=normalized_symbols,
        metrics=metrics,
    )
