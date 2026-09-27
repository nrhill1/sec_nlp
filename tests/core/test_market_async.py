# tests/core/test_market_async.py
"""Tests for cancellable fresh market requests sharing one native session."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest

from sec_nlp.core import market


def test_async_market_reuses_session_and_bypasses_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create one lazy connector but fetch every explicit refresh from its provider."""
    row = {
        "timestamp": 1,
        "open_price": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "adjclose": 1.0,
        "volume": 2,
    }
    fetch = AsyncMock(return_value=[row])
    constructor = Mock(return_value=Mock(retrieve_range_async=fetch))
    native = Mock(
        MarketSession=constructor,
        retrieve_range=Mock(side_effect=AssertionError("sync request")),
    )
    monkeypatch.setattr(
        market, "_load_market_module", Mock(return_value=native)
    )
    retriever = market.MarketRetriever()
    constructor.assert_not_called()

    async def exercise() -> None:
        """Refresh twice while retaining the same provider session."""
        for _ in range(2):
            quotes = await retriever.retrieve_range_async(
                "SPY", (date(2026, 1, 1), date(2026, 1, 2))
            )
            assert quotes[0].close == 1.0

    asyncio.run(exercise())
    constructor.assert_called_once_with()
    assert fetch.await_count == 2
    assert (
        retriever.retrieve_range("SPY", (date(2026, 1, 1), date(2026, 1, 2)))[
            0
        ].volume
        == 2
    )


def test_async_market_cancellation_waits_for_native_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not finish a cancelled adapter request until the native session is idle."""

    async def exercise() -> None:
        """Separate Python future cancellation from native cleanup acknowledgement."""
        started = asyncio.Event()
        cancelled = asyncio.Event()
        acknowledged = asyncio.Event()

        async def fetch(ticker: str, span: str) -> list[dict[str, float | int]]:
            """Wait until the parent cancels the future returned by the native client."""
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
            return []

        async def wait_idle() -> None:
            """Complete native cleanup after the original awaitable was cancelled."""
            assert cancelled.is_set()
            await asyncio.sleep(0)
            acknowledged.set()

        monkeypatch.setattr(
            market,
            "_load_market_module",
            Mock(
                return_value=Mock(
                    MarketSession=Mock(
                        return_value=Mock(
                            retrieve_range_async=fetch,
                            wait_idle_async=wait_idle,
                        )
                    )
                )
            ),
        )
        retriever = market.MarketRetriever()
        task = asyncio.create_task(
            retriever.retrieve_range_async(
                "SPY", (date(2026, 1, 1), date(2026, 1, 2))
            )
        )
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert acknowledged.is_set()

    asyncio.run(exercise())


@pytest.mark.parametrize("cancel_again", [False, True])
def test_timeout_cleanup_gates_new_market_requests(
    monkeypatch: pytest.MonkeyPatch,
    cancel_again: bool,
) -> None:
    """Keep queued work out of a draining session and await repeated cancellation."""

    async def exercise() -> None:
        """Hold native cleanup open while a queued source attempts admission."""
        started = asyncio.Event()
        draining = asyncio.Event()
        release = asyncio.Event()
        admitted: list[str] = []
        idle_calls = 0

        async def fetch(ticker: str, span: str) -> list[dict[str, float | int]]:
            """Leave the initial request pending until its deadline cancels it."""
            admitted.append(ticker)
            if ticker == "FIRST":
                started.set()
                await asyncio.Event().wait()
            return []

        async def wait_idle() -> None:
            """Represent native cleanup separately from Python cancellation."""
            nonlocal idle_calls
            idle_calls += 1
            draining.set()
            await release.wait()

        monkeypatch.setattr(
            market,
            "_load_market_module",
            Mock(
                return_value=Mock(
                    MarketSession=Mock(
                        return_value=Mock(
                            retrieve_range_async=fetch,
                            wait_idle_async=wait_idle,
                        )
                    )
                )
            ),
        )
        retriever = market.MarketRetriever()
        span = (date(2026, 1, 1), date(2026, 1, 2))

        async def deadline_request() -> None:
            """Expire an explicit request deadline after its native request starts."""
            async with asyncio.timeout(None) as deadline:
                request = asyncio.create_task(
                    retriever.retrieve_range_async("FIRST", span)
                )
                await started.wait()
                deadline.reschedule(asyncio.get_running_loop().time())
                await request

        first = asyncio.create_task(deadline_request())
        await asyncio.wait_for(draining.wait(), 1)
        queued = asyncio.create_task(
            retriever.retrieve_range_async("QUEUED", span)
        )
        await asyncio.sleep(0)
        assert admitted == ["FIRST"] and not first.done()
        # A user cancellation arriving during deadline cleanup must not cancel
        # the native acknowledgement future or admit queued requests early.
        if cancel_again:
            first.cancel()
        await asyncio.sleep(0)
        assert not first.done() and not queued.done()
        release.set()
        with pytest.raises(
            asyncio.CancelledError if cancel_again else TimeoutError
        ):
            await first
        assert await queued == []
        assert admitted == ["FIRST", "QUEUED"] and idle_calls == 1

    asyncio.run(exercise())
