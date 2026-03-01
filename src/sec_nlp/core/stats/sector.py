# src/sec_nlp/core/stats/sector.py
"""Sector-level correlation helpers built on top of core stats wrappers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from sec_nlp.core.market import (
    MarketQuote,
    create_market_retriever,
)

from .correlation import CorrExtensionError, pearson, simple_returns


class MarketRangeRetriever(Protocol):
    """Duck-typed market retriever dependency used by sector helpers."""

    def retrieve_range(
        self,
        ticker: str,
        date_range: Sequence[date | datetime],
    ) -> list[MarketQuote]: ...


def _coerce_as_of(value: date | datetime | None) -> date:
    """Coerce as of."""
    if value is None:
        return datetime.now(UTC).date()
    if isinstance(value, datetime):
        return value.date()
    return value


def _resolve_sic(
    symbol: str,
    symbol_to_sic: Mapping[str, str] | Callable[[str], str | None] | None,
) -> str:
    """Resolve sic."""
    if symbol_to_sic is None:
        return "UNKNOWN"
    if isinstance(symbol_to_sic, Mapping):
        raw_value: str | None = None
        lookup = symbol.upper()
        for mapping_key, mapping_value in symbol_to_sic.items():
            if (
                isinstance(mapping_key, str)
                and isinstance(mapping_value, str)
                and mapping_key.upper() == lookup
            ):
                raw_value = mapping_value
                break
    else:
        raw_value = symbol_to_sic(symbol)
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if cleaned:
            return cleaned
    return "UNKNOWN"


def _extract_returns(
    quotes: Sequence[MarketQuote],
) -> tuple[dict[int, float], list[float]]:
    """Extract returns."""
    ordered = sorted(quotes, key=lambda quote: quote.timestamp)
    closes = [quote.close for quote in ordered]
    if len(closes) < 2:
        return {}, []
    try:
        returns = simple_returns(closes)
    except CorrExtensionError:
        returns = _simple_returns_fallback(closes)
    except ValueError:
        returns = []
    if not returns:
        return {}, []
    # Return at index i corresponds to timestamp i + 1 in the original series.
    timestamped = {
        int(ordered[index + 1].timestamp): value
        for index, value in enumerate(returns)
    }
    return timestamped, returns


def _simple_returns_fallback(closes: Sequence[float]) -> list[float]:
    """Resolve simple returns fallback."""
    if len(closes) < 2:
        return []
    output: list[float] = []
    for prev_close, close in zip(closes, closes[1:], strict=False):
        if prev_close == 0:
            continue
        output.append((close / prev_close) - 1.0)
    return output


def _pearson_fallback(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Resolve pearson fallback."""
    if len(x) != len(y) or len(x) < 2:
        return None
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)

    cov = 0.0
    var_x = 0.0
    var_y = 0.0
    for xv, yv in zip(x, y, strict=True):
        dx = xv - mean_x
        dy = yv - mean_y
        cov += dx * dy
        var_x += dx * dx
        var_y += dy * dy

    if var_x == 0.0 or var_y == 0.0:
        return None
    return cov / ((var_x**0.5) * (var_y**0.5))


def _pairwise_correlation(
    left: dict[int, float],
    right: dict[int, float],
) -> float | None:
    """Resolve pairwise correlation."""
    common_timestamps = sorted(set(left) & set(right))
    if len(common_timestamps) < 2:
        return None
    x = [left[timestamp] for timestamp in common_timestamps]
    y = [right[timestamp] for timestamp in common_timestamps]
    try:
        return pearson(x, y)
    except CorrExtensionError:
        return _pearson_fallback(x, y)
    except ValueError:
        return None


class SectorCorrelation(BaseModel):
    """Pairwise return-correlation output for one SIC group."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    sic_code: str
    symbols: list[str]
    correlation_matrix: dict[str, dict[str, float | None]]


def sector_correlation(
    symbols: Sequence[str],
    *,
    metric: str = "price_return",
    days: int = 252,
    as_of: date | datetime | None = None,
    symbol_to_sic: Mapping[str, str]
    | Callable[[str], str | None]
    | None = None,
    retriever: MarketRangeRetriever | None = None,
) -> list[SectorCorrelation]:
    """Compute sector-wise pairwise correlation matrices.

    `symbol_to_sic` can be either a mapping (`{"AAPL": "3571"}`) or a resolver
    callback that accepts a symbol and returns a SIC code.
    """
    if metric != "price_return":
        raise ValueError("only metric='price_return' is currently supported")
    if days < 2:
        raise ValueError("days must be >= 2")

    normalized_symbols = sorted(
        {symbol.strip().upper() for symbol in symbols if symbol.strip()}
    )
    if not normalized_symbols:
        return []

    end_date = _coerce_as_of(as_of)
    start_date = end_date - timedelta(days=days)
    retriever_instance = retriever or create_market_retriever()

    returns_by_symbol: dict[str, dict[int, float]] = {}
    sic_by_symbol: dict[str, str] = {}

    for symbol in normalized_symbols:
        quotes = retriever_instance.retrieve_range(
            symbol, (start_date, end_date)
        )
        timestamped_returns, raw_returns = _extract_returns(quotes)
        if not raw_returns:
            continue
        returns_by_symbol[symbol] = timestamped_returns
        sic_by_symbol[symbol] = _resolve_sic(symbol, symbol_to_sic)

    if not returns_by_symbol:
        return []

    by_sector: dict[str, list[str]] = {}
    for symbol, sic_code in sic_by_symbol.items():
        by_sector.setdefault(sic_code, []).append(symbol)

    outputs: list[SectorCorrelation] = []
    for sic_code in sorted(by_sector):
        sector_symbols = sorted(by_sector[sic_code])
        matrix: dict[str, dict[str, float | None]] = {}
        for row_symbol in sector_symbols:
            row: dict[str, float | None] = {}
            for col_symbol in sector_symbols:
                if row_symbol == col_symbol:
                    row[col_symbol] = 1.0
                else:
                    row[col_symbol] = _pairwise_correlation(
                        returns_by_symbol[row_symbol],
                        returns_by_symbol[col_symbol],
                    )
            matrix[row_symbol] = row

        outputs.append(
            SectorCorrelation(
                sic_code=sic_code,
                symbols=sector_symbols,
                correlation_matrix=matrix,
            )
        )

    return outputs
