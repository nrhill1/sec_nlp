# tests/pipelines/async_support/test_mixin.py
"""Tests for async pipeline support.

Note: Tests that require running async code are skipped because
pytest-socket blocks socket usage, and asyncio event loops use sockets
for their internal self-pipe mechanism.
"""

import asyncio
from typing import Literal

import pytest

from sec_nlp.pipelines.async_support import (
    AsyncPipelineRunner,
    AsyncSymbolProcessor,
    determine_async_mode,
)

# Mark tests that require running async code (which needs sockets for event loop)
requires_socket = pytest.mark.skip(
    reason="Async event loops require sockets which are blocked by pytest-socket"
)


class TestAsyncPipelineRunner:
    """Tests for AsyncPipelineRunner."""

    def test_should_use_async_sync_mode(self) -> None:
        """Test that sync mode always returns False."""
        runner = AsyncPipelineRunner()
        assert (
            runner.should_use_async("sync", num_symbols=10, num_files=100)
            is False
        )

    def test_should_use_async_async_mode(self) -> None:
        """Test that async mode always returns True."""
        runner = AsyncPipelineRunner()
        assert (
            runner.should_use_async("async", num_symbols=1, num_files=1) is True
        )

    def test_should_use_async_auto_mode_few_items(self) -> None:
        """Test auto mode with few items returns False."""
        runner = AsyncPipelineRunner()
        assert (
            runner.should_use_async("auto", num_symbols=1, num_files=5) is False
        )

    def test_should_use_async_auto_mode_many_symbols(self) -> None:
        """Test auto mode with many symbols returns True."""
        runner = AsyncPipelineRunner()
        assert (
            runner.should_use_async("auto", num_symbols=5, num_files=1) is True
        )

    def test_should_use_async_auto_mode_many_files(self) -> None:
        """Test auto mode with many files returns True."""
        runner = AsyncPipelineRunner()
        assert (
            runner.should_use_async("auto", num_symbols=1, num_files=15) is True
        )

    def test_should_use_async_boundary_conditions(self) -> None:
        """Test auto mode boundary conditions."""
        runner = AsyncPipelineRunner()
        # Exact thresholds (symbols >= 3, files >= 10)
        assert (
            runner.should_use_async("auto", num_symbols=3, num_files=0) is True
        )
        assert (
            runner.should_use_async("auto", num_symbols=2, num_files=0) is False
        )
        assert (
            runner.should_use_async("auto", num_symbols=0, num_files=10) is True
        )
        assert (
            runner.should_use_async("auto", num_symbols=0, num_files=9) is False
        )

    @requires_socket
    def test_get_async_semaphore_creates_new(self) -> None:
        """Test that semaphore is created on first access."""
        runner = AsyncPipelineRunner()
        semaphore = runner._get_async_semaphore(max_concurrent=3)

        assert isinstance(semaphore, asyncio.Semaphore)
        assert semaphore._value == 3

    @requires_socket
    def test_get_async_semaphore_reuses_existing(self) -> None:
        """Test that same semaphore is returned on subsequent calls."""
        runner = AsyncPipelineRunner()
        sem1 = runner._get_async_semaphore(max_concurrent=3)
        sem2 = runner._get_async_semaphore(max_concurrent=5)  # Different value

        assert sem1 is sem2  # Same instance

    @requires_socket
    def test_gather_with_semaphore(self) -> None:
        """Test gather_with_semaphore executes coroutines."""

        async def run_test() -> list[int | BaseException]:
            semaphore = asyncio.Semaphore(2)

            async def sample_coro(x: int) -> int:
                return x * 2

            coros = [sample_coro(i) for i in range(5)]
            return await AsyncPipelineRunner.gather_with_semaphore(
                semaphore, coros
            )

        results = AsyncPipelineRunner.run_async_in_new_loop(run_test())
        assert results == [0, 2, 4, 6, 8]

    @requires_socket
    def test_gather_with_semaphore_handles_exceptions(self) -> None:
        """Test gather_with_semaphore returns exceptions when configured."""

        async def run_test() -> list[int | BaseException]:
            semaphore = asyncio.Semaphore(2)

            async def failing_coro() -> int:
                raise ValueError("test error")

            async def success_coro() -> int:
                return 42

            coros = [success_coro(), failing_coro(), success_coro()]
            return await AsyncPipelineRunner.gather_with_semaphore(
                semaphore, coros, return_exceptions=True
            )

        results = AsyncPipelineRunner.run_async_in_new_loop(run_test())
        assert results[0] == 42
        assert isinstance(results[1], ValueError)
        assert results[2] == 42

    @requires_socket
    def test_to_thread(self) -> None:
        """Test running sync function in thread pool."""

        async def run_test() -> int:
            def sync_function(x: int, y: int) -> int:
                return x + y

            return await AsyncPipelineRunner.to_thread(sync_function, 5, 3)

        result = AsyncPipelineRunner.run_async_in_new_loop(run_test())
        assert result == 8


class TestAsyncSymbolProcessor:
    """Tests for AsyncSymbolProcessor."""

    def test_init_with_defaults(self) -> None:
        """Test AsyncSymbolProcessor initialization with defaults."""
        processor = AsyncSymbolProcessor()
        # Check internal attributes (default max_concurrent=4, verbose=True)
        assert processor._semaphore._value == 4
        assert processor._verbose is True

    def test_init_with_custom_values(self) -> None:
        """Test AsyncSymbolProcessor initialization with custom values."""
        processor = AsyncSymbolProcessor(max_concurrent=10, verbose=False)
        assert processor._semaphore._value == 10
        assert processor._verbose is False

    @requires_socket
    def test_process_symbols_success(self) -> None:
        """Test processing symbols successfully."""

        async def run_test() -> dict[str, dict[str, str | int]]:
            async def process_func(symbol: str) -> dict[str, str | int]:
                return {"symbol": symbol, "value": len(symbol)}

            processor = AsyncSymbolProcessor(max_concurrent=2, verbose=False)
            return await processor.process_symbols(
                symbols=["AAPL", "MSFT", "TSLA"],
                process_func=process_func,
            )

        results = AsyncPipelineRunner.run_async_in_new_loop(run_test())
        assert len(results) == 3
        assert results["AAPL"] == {"symbol": "AAPL", "value": 4}
        assert results["MSFT"] == {"symbol": "MSFT", "value": 4}
        assert results["TSLA"] == {"symbol": "TSLA", "value": 4}

    @requires_socket
    def test_process_symbols_with_failure(self) -> None:
        """Test processing symbols with one failure."""

        async def run_test() -> dict[str, dict[str, str]]:
            async def process_func(symbol: str) -> dict[str, str]:
                if symbol == "FAIL":
                    raise ValueError(f"Failed for {symbol}")
                return {"symbol": symbol}

            processor = AsyncSymbolProcessor(max_concurrent=2, verbose=False)
            return await processor.process_symbols(
                symbols=["AAPL", "FAIL", "TSLA"],
                process_func=process_func,
            )

        results = AsyncPipelineRunner.run_async_in_new_loop(run_test())
        # Should have results for non-failing symbols
        assert "AAPL" in results
        assert "TSLA" in results
        assert "FAIL" not in results

    @requires_socket
    def test_process_symbols_respects_concurrency(self) -> None:
        """Test that concurrency limit is respected."""

        async def run_test() -> int:
            concurrent_count = 0
            max_concurrent_observed = 0

            async def process_func(symbol: str) -> dict[str, str]:
                nonlocal concurrent_count, max_concurrent_observed
                concurrent_count += 1
                max_concurrent_observed = max(
                    max_concurrent_observed, concurrent_count
                )
                await asyncio.sleep(0.02)  # Ensure overlap
                concurrent_count -= 1
                return {"symbol": symbol}

            processor = AsyncSymbolProcessor(max_concurrent=2, verbose=False)
            await processor.process_symbols(
                symbols=["A", "B", "C", "D", "E"],
                process_func=process_func,
            )
            return max_concurrent_observed

        max_observed = AsyncPipelineRunner.run_async_in_new_loop(run_test())
        # Should never exceed max_concurrent
        assert max_observed <= 2


class TestDetermineAsyncMode:
    """Tests for determine_async_mode function."""

    def test_sync_mode_always_false(self) -> None:
        """Test sync mode always returns False."""
        assert determine_async_mode("sync") is False
        assert determine_async_mode("sync", num_symbols=100) is False

    def test_async_mode_always_true(self) -> None:
        """Test async mode always returns True."""
        assert determine_async_mode("async") is True
        assert determine_async_mode("async", num_symbols=1) is True

    def test_auto_mode_many_symbols(self) -> None:
        """Test auto mode with many symbols."""
        assert determine_async_mode("auto", num_symbols=3) is True
        assert determine_async_mode("auto", num_symbols=2) is False

    def test_auto_mode_many_files(self) -> None:
        """Test auto mode with many files."""
        assert determine_async_mode("auto", num_files_estimate=10) is True
        assert determine_async_mode("auto", num_files_estimate=9) is False

    def test_auto_mode_queries_with_files(self) -> None:
        """Test auto mode with queries and files."""
        assert (
            determine_async_mode(
                "auto", has_multiple_queries=True, num_files_estimate=5
            )
            is True
        )
        assert (
            determine_async_mode(
                "auto", has_multiple_queries=True, num_files_estimate=4
            )
            is False
        )
        assert (
            determine_async_mode(
                "auto", has_multiple_queries=False, num_files_estimate=5
            )
            is False
        )
