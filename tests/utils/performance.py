# tests/utils/performance.py
"""Helpers for memory tracking and lightweight benchmark comparisons."""

from __future__ import annotations

import contextlib
import time
import tracemalloc
from collections.abc import Callable, Generator, Iterable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def compare_benchmark(
    current: float,
    baseline: float,
    tolerance: float = 0.10,
) -> bool:
    """Return True if current runtime is within tolerance of baseline."""
    if baseline <= 0:
        return True

    ratio = current / baseline
    return ratio <= (1 + tolerance)


def measure_duration(
    func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> tuple[T, float]:
    """Execute a callable and return (result, seconds)."""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


@contextlib.contextmanager
def memory_tracker() -> Generator[dict[str, int]]:
    """Track current and peak memory deltas using tracemalloc."""
    tracemalloc.start()
    start_current, start_peak = tracemalloc.get_traced_memory()
    metrics = {"delta": 0, "peak": 0}
    try:
        yield metrics
    finally:
        end_current, end_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        metrics["delta"] = end_current - start_current
        metrics["peak"] = end_peak - start_peak


def chunked[T](iterable: Iterable[T], size: int) -> list[list[T]]:
    """Simple chunking helper for tests (avoids pulling production code)."""
    chunk: list[T] = []
    batches: list[list[T]] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            batches.append(chunk)
            chunk = []
    if chunk:
        batches.append(chunk)
    return batches
