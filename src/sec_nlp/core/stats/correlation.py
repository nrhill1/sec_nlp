# src/sec_nlp/core/stats/correlation.py
"""Thin wrapper around the Rust `corr` extension."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from importlib import import_module
from types import ModuleType


class CorrExtensionError(RuntimeError):
    """Raised when the Rust `corr` extension is unavailable."""


@lru_cache(maxsize=1)
def _load_corr_module() -> ModuleType:
    """Load optional native correlation extension module."""
    try:
        return import_module("corr")
    except Exception as exc:  # pragma: no cover - depends on extension install
        raise CorrExtensionError(
            "corr extension is not available; build it with `make rs-corr-dev` "
            "or `make build-ext`."
        ) from exc


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Pearson correlation between two series."""
    return _load_corr_module().pearson(list(x), list(y))


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Spearman rank correlation between two series."""
    return _load_corr_module().spearman(list(x), list(y))


def simple_returns(prices: Sequence[float]) -> list[float]:
    """Compute simple returns from a price series."""
    return list(_load_corr_module().simple_returns(list(prices)))


def cumulative_return(prices: Sequence[float]) -> float | None:
    """Compute cumulative return over a price series."""
    return _load_corr_module().cumulative_return(list(prices))


def car(
    asset_prices: Sequence[float], benchmark_prices: Sequence[float]
) -> float | None:
    """Compute cumulative abnormal return (asset - benchmark)."""
    return _load_corr_module().car(list(asset_prices), list(benchmark_prices))


def rolling_returns(prices: Sequence[float], window: int) -> list[float]:
    """Compute rolling cumulative returns for a window size."""
    return list(_load_corr_module().rolling_returns(list(prices), int(window)))


def std_dev(values: Sequence[float]) -> float:
    """Compute population standard deviation for a series."""
    return _load_corr_module().std_dev(list(values))


def volume_spike(values: Sequence[float]) -> float | None:
    """Compute max/average ratio for a series, typically volumes."""
    return _load_corr_module().volume_spike(list(values))


def average_true_range(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
) -> float:
    """Compute average true range (ATR) for OHLC data."""
    return _load_corr_module().average_true_range(
        list(high), list(low), list(close)
    )


def garman_klass(
    high: Sequence[float],
    low: Sequence[float],
    open: Sequence[float],
    close: Sequence[float],
) -> float:
    """Compute Garman-Klass volatility estimator for OHLC data."""
    return _load_corr_module().garman_klass(
        list(high), list(low), list(open), list(close)
    )


def beta(
    asset_returns: Sequence[float], benchmark_returns: Sequence[float]
) -> float:
    """Compute beta vs. a benchmark return series."""
    return _load_corr_module().beta(
        list(asset_returns), list(benchmark_returns)
    )


def event_study(
    prices: Sequence[float],
    timestamps: Sequence[int],
    event_timestamp: int,
    pre_window: int,
    post_window: int,
):
    """Run a simple pre/post event study over price series."""
    return _load_corr_module().event_study(
        list(prices),
        list(timestamps),
        int(event_timestamp),
        int(pre_window),
        int(post_window),
    )
