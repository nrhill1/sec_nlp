# src/scripts/profile/utils.py
"""Profiling utilities for performance measurement."""

import cProfile
import functools
import io
import pstats
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import ParamSpec, Self

from sec_nlp.core.infra.logger import logger

P = ParamSpec("P")


@contextmanager
def timer(name: str, log: bool = True) -> Generator[None]:
    """
    Simple timing context manager.

    Usage:
        with timer("my operation"):
            # ... code to time
    """
    start = time.perf_counter()
    try:
        yield None
    finally:
        duration = time.perf_counter() - start
        if log:
            logger.info(
                "⏱️  %s: %.3fs (%.0fms)", name, duration, duration * 1000
            )


def profile_func[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator to profile a function.

    Usage:
        @profile_func
        def my_function():
            ...
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        profiler = cProfile.Profile()
        profiler.enable()

        try:
            return func(*args, **kwargs)
        finally:
            profiler.disable()

            # Print stats
            s = io.StringIO()
            ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
            ps.print_stats(20)
            output = s.getvalue().strip()
            logger.info("=== Profile for %s ===", func.__name__)
            if output:
                for line in output.splitlines():
                    logger.info(line)

    return wrapper


class Profiler:
    """Context manager for profiling code blocks."""

    def __init__(
        self,
        output_file: Path | None = None,
        sort_by: str = "cumulative",
        print_stats: bool = True,
        top_n: int = 30,
    ):
        """
        Initialize profiler.

        Args:
            output_file: Optional file to save profile data
            sort_by: Sorting criteria (cumulative, time, calls, etc.)
            print_stats: Whether to print stats after profiling
            top_n: Number of top functions to display
        """
        self.output_file = output_file
        self.sort_by = sort_by
        self.print_stats = print_stats
        self.top_n = top_n
        self.profiler = cProfile.Profile()

    def __enter__(self) -> Self:
        """Start profiling."""
        self.profiler.enable()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop profiling and optionally save/print results."""
        self.profiler.disable()

        stats = pstats.Stats(self.profiler)
        stats.sort_stats(self.sort_by)

        if self.output_file:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            stats.dump_stats(str(self.output_file))
            logger.info("Profile saved to: %s", self.output_file)

        if self.print_stats:
            s = io.StringIO()
            ps = pstats.Stats(self.profiler, stream=s)
            ps.strip_dirs().sort_stats(self.sort_by)
            # Focus on sec_nlp functions to avoid noise from primitives
            ps.print_stats("sec_nlp", self.top_n)
            output = s.getvalue().strip()
            if not output:
                # Fallback to standard top_n if nothing matched
                ps = pstats.Stats(self.profiler, stream=s)
                ps.sort_stats(self.sort_by)
                ps.print_stats(self.top_n)
                output = s.getvalue().strip()
            logger.info("=== Profiling Results ===")
            if output:
                for line in output.splitlines():
                    logger.info(line)

    def get_stats(self) -> pstats.Stats:
        """Get statistics object for further analysis."""
        return pstats.Stats(self.profiler)
