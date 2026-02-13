"""Manual stub for the `corr` native extension."""

from __future__ import annotations

from collections.abc import Sequence

class EventStudyResult:
    car_pre: float | None
    car_post: float | None
    t_stat: float | None
    p_value: float | None

def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Pearson correlation between two series."""

def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Spearman rank correlation between two series."""

def simple_returns(prices: Sequence[float]) -> list[float]:
    """Compute simple returns from a price series."""

def cumulative_return(prices: Sequence[float]) -> float | None:
    """Compute cumulative return over a price series."""

def car(
    asset_prices: Sequence[float], benchmark_prices: Sequence[float]
) -> float | None:
    """Compute cumulative abnormal return (asset - benchmark)."""

def rolling_returns(prices: Sequence[float], window: int) -> list[float]:
    """Compute rolling cumulative returns for a window size."""

def std_dev(values: Sequence[float]) -> float:
    """Compute population standard deviation for a series."""

def volume_spike(values: Sequence[float]) -> float | None:
    """Compute max/average ratio for a series, typically volumes."""

def average_true_range(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
) -> float:
    """Compute average true range (ATR) for OHLC data."""

def garman_klass(
    high: Sequence[float],
    low: Sequence[float],
    open: Sequence[float],
    close: Sequence[float],
) -> float:
    """Compute Garman-Klass volatility estimator for OHLC data."""

def beta(
    asset_returns: Sequence[float], benchmark_returns: Sequence[float]
) -> float:
    """Compute beta vs. a benchmark return series."""

def event_study(
    prices: Sequence[float],
    timestamps: Sequence[int],
    event_timestamp: int,
    pre_window: int,
    post_window: int,
) -> EventStudyResult:
    """Run a simple pre/post event study over price series."""
