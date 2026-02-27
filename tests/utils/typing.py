# tests/utils/typing.py
"""Typing helpers for test fixtures and benchmarks."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import ParamSpec, Protocol  # noqa: UP035

P = ParamSpec("P")


class Benchmark(Protocol):
    def __call__[**P, T](
        self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> T: ...


class BenchmarkCompare(Protocol):
    def __call__(
        self, current: float, baseline: float, tolerance: float = 0.10
    ) -> bool: ...


class MemoryTracker(Protocol):
    def __call__(self) -> AbstractContextManager[dict[str, int]]: ...
