# src/sec_nlp/pipelines/async_support/mixin.py
"""Async pipeline mixin for concurrent processing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from typing import Literal

from sec_nlp.core.infra.logger import logger

type AsyncMode = Literal["sync", "async", "auto"]


class AsyncPipelineRunner:
    """Async execution support for pipelines.

    Provides async variants of pipeline methods and infrastructure
    for concurrent processing with semaphore-based rate limiting.

    Example:
        class MyPipeline(BasePipeline):
            def __init__(self, ...):
                self._async_runner = AsyncPipelineRunner()

            async def run_async(self) -> MyResult:
                # Use self._async_runner for async operations
                pass
    """

    _async_semaphore: asyncio.Semaphore | None = None
    _default_max_concurrent: int = 4

    def _get_async_semaphore(
        self, max_concurrent: int | None = None
    ) -> asyncio.Semaphore:
        """Get or create an async semaphore for rate limiting.

        Args:
            max_concurrent: Maximum concurrent operations (uses default if None)

        Returns:
            Semaphore for rate limiting concurrent operations
        """
        limit = max_concurrent or self._default_max_concurrent
        if self._async_semaphore is None:
            self._async_semaphore = asyncio.Semaphore(limit)
        return self._async_semaphore

    def should_use_async(
        self,
        mode: AsyncMode,
        *,
        num_symbols: int = 1,
        num_files: int = 1,
    ) -> bool:
        """Determine if async execution would be beneficial.

        Args:
            mode: Async mode setting (sync, async, or auto)
            num_symbols: Number of symbols to process
            num_files: Estimated number of files to process

        Returns:
            True if async should be used
        """
        if mode == "sync":
            return False
        if mode == "async":
            return True

        # Auto mode: use async when there's enough work to parallelize
        # Rule of thumb: async is beneficial with 3+ symbols or 10+ files
        return num_symbols >= 3 or num_files >= 10

    @staticmethod
    async def gather_with_semaphore[T](
        semaphore: asyncio.Semaphore,
        coros: Sequence[Awaitable[T]],
        *,
        return_exceptions: bool = True,
    ) -> list[T | BaseException]:
        """Execute coroutines with semaphore-based rate limiting.

        Args:
            semaphore: Semaphore for rate limiting
            coros: List of coroutines to execute
            return_exceptions: Whether to return exceptions instead of raising

        Returns:
            List of results from all coroutines (may include exceptions)
        """

        async def limited_coro(
            index: int, coro: Awaitable[T]
        ) -> tuple[int, T | None, BaseException | None]:
            async with semaphore:
                try:
                    return index, await coro, None
                except BaseException as exc:  # pragma: no cover - passthrough
                    return index, None, exc

        if not coros:
            return []

        tasks = [
            asyncio.create_task(limited_coro(index, coro))
            for index, coro in enumerate(coros)
        ]
        ordered: dict[int, T | BaseException | None] = dict.fromkeys(
            range(len(coros))
        )

        try:
            for task in asyncio.as_completed(tasks):
                index, value, exc = await task
                if exc is not None:
                    if return_exceptions:
                        ordered[index] = exc
                        continue
                    for pending in tasks:
                        if not pending.done():
                            pending.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise exc

                ordered[index] = value
        finally:
            await asyncio.gather(*tasks, return_exceptions=True)

        results: list[T | BaseException] = []
        for index in range(len(coros)):
            value = ordered[index]
            if value is None:
                results.append(RuntimeError("task did not complete"))
                continue
            results.append(value)
        return results

    @staticmethod
    def run_async_in_new_loop[T](coro: Coroutine[None, None, T]) -> T:
        """Run an async coroutine in a new event loop.

        This is useful for calling async code from sync contexts
        when there's no existing event loop.

        Args:
            coro: Coroutine to run

        Returns:
            Result from the coroutine
        """
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except (RuntimeError, ValueError):
                    pass
                shutdown_default_executor = getattr(
                    loop, "shutdown_default_executor", None
                )
                if callable(shutdown_default_executor):
                    try:
                        loop.run_until_complete(shutdown_default_executor())
                    except (RuntimeError, ValueError):
                        pass
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    @staticmethod
    async def to_thread[T](
        func: Callable[..., T],
        *args: T,
        **kwargs: T,
    ) -> T:
        """Run a sync function in a thread pool.

        This is a thin wrapper around asyncio.to_thread for
        compatibility and clarity.

        Args:
            func: Synchronous function to run
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result from the function
        """
        return await asyncio.to_thread(func, *args, **kwargs)


class AsyncSymbolProcessor:
    """Processes multiple symbols concurrently with progress tracking.

    Example:
        processor = AsyncSymbolProcessor(max_concurrent=4)
        results = await processor.process_symbols(
            symbols=["AAPL", "MSFT", "TSLA"],
            process_func=pipeline._process_symbol_async,
        )
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        *,
        verbose: bool = True,
    ) -> None:
        """Initialize the processor.

        Args:
            max_concurrent: Maximum concurrent symbol processing
            verbose: Enable verbose logging
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._verbose = verbose
        self._completed = 0
        self._total = 0

    async def process_symbols[T](
        self,
        symbols: list[str],
        process_func: Callable[[str], Coroutine[None, None, T]],
    ) -> dict[str, T]:
        """Process multiple symbols concurrently.

        Args:
            symbols: List of symbols to process
            process_func: Async function taking a symbol and returning a result

        Returns:
            Dictionary mapping symbols to their results
        """
        self._total = len(symbols)
        self._completed = 0

        if self._verbose:
            logger.info(
                "Processing %d symbols concurrently (max=%d)",
                self._total,
                self._semaphore._value,
            )

        async def process_with_tracking(symbol: str) -> tuple[str, T]:
            async with self._semaphore:
                try:
                    result = await process_func(symbol)
                    self._completed += 1
                    if self._verbose:
                        logger.info(
                            "Completed %s (%d/%d)",
                            symbol,
                            self._completed,
                            self._total,
                        )
                    return symbol, result
                except Exception as e:
                    self._completed += 1
                    logger.error("Failed to process %s: %s", symbol, e)
                    raise

        async def process_with_error_capture(
            symbol: str,
        ) -> tuple[str, T | BaseException]:
            try:
                return await process_with_tracking(symbol)
            except BaseException as exc:
                return symbol, exc

        result_dict: dict[str, T] = {}
        tasks = [
            asyncio.create_task(process_with_error_capture(symbol))
            for symbol in symbols
        ]
        for task in asyncio.as_completed(tasks):
            symbol, value = await task
            if isinstance(value, BaseException):
                logger.error(
                    "Symbol %s failed with exception: %s", symbol, value
                )
                continue
            result_dict[symbol] = value

        return result_dict


def determine_async_mode(
    mode: AsyncMode,
    *,
    num_symbols: int = 1,
    num_files_estimate: int = 1,
    has_multiple_queries: bool = False,
) -> bool:
    """Determine whether to use async based on mode and workload.

    Args:
        mode: Configured async mode
        num_symbols: Number of symbols to process
        num_files_estimate: Estimated number of files
        has_multiple_queries: Whether there are multiple search queries

    Returns:
        True if async should be used
    """
    if mode == "sync":
        return False
    if mode == "async":
        return True

    # Auto mode heuristics
    # Async is beneficial when there's parallelizable I/O work
    if num_symbols >= 3:
        return True
    if num_files_estimate >= 10:
        return True
    return has_multiple_queries and num_files_estimate >= 5
