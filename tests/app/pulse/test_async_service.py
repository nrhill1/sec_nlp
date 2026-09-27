# tests/app/pulse/test_async_service.py
"""Tests for Pulse's bounded asynchronous sources and durable cancellation handoff.

Providers remain offline fakes. The tests assert request cleanup, incremental
callbacks, and bounded work rather than relying on timing-only performance gates.
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import HttpUrl

from sec_nlp.app.pulse import service
from sec_nlp.app.pulse.models import Feed, PulseSettings, WatchItem
from sec_nlp.core.market import MarketQuote
from sec_nlp.core.news.client import NewsItem

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)


def _quote() -> MarketQuote:
    """Supply one valid cached-looking session from an explicitly called provider."""
    return MarketQuote(
        timestamp=int(datetime(2026, 9, 25, tzinfo=UTC).timestamp()),
        open_price=99,
        high=101,
        low=98,
        close=100,
        volume=5,
        adjclose=100,
    )


def test_market_and_news_share_four_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bound combined source activity and report each finished source once."""

    async def exercise() -> None:
        """Gate all providers until the first four operations are active."""
        active = 0
        maximum = 0
        entered = asyncio.Event()
        release = asyncio.Event()
        delivered: list[tuple[str, int, int]] = []

        async def wait_provider() -> None:
            """Record active underlying requests until explicitly released."""
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            if active == 4:
                entered.set()
            try:
                await release.wait()
                await asyncio.sleep(0)
            finally:
                active -= 1

        async def market(
            ticker: str, dates: Sequence[date | datetime]
        ) -> list[MarketQuote]:
            """Return one quote after sharing the global source gate."""
            await wait_provider()
            return [_quote()]

        async def news(
            *, keywords: list[str], max_results: int, sec_transport
        ) -> list[NewsItem]:
            """Return a headline through the same concurrency gate as market."""
            await wait_provider()
            return [
                NewsItem(
                    title="Useful news",
                    url="https://example.com/news",
                    source="fixture",
                )
            ]

        async def completed(
            result: service.SourceResult, count: int, total: int
        ) -> None:
            """Capture typed progress after evidence is available."""
            delivered.append((result.status.name, count, total))

        monkeypatch.setattr(
            service,
            "create_market_retriever",
            Mock(return_value=Mock(retrieve_range_async=market)),
        )
        monkeypatch.setattr(
            service,
            "create_news_retriever",
            Mock(return_value=Mock(fetch_async=news)),
        )
        settings = PulseSettings(
            watchlist=tuple(
                WatchItem(symbol=f"SYM{index}") for index in range(8)
            ),
            benchmarks=(),
            company_feeds=False,
            feeds=(
                Feed(name="News A", url=HttpUrl("https://example.com/a")),
                Feed(name="News B", url=HttpUrl("https://example.com/b")),
            ),
        )
        task = asyncio.create_task(
            service.build_brief_async(settings, now=NOW, on_source=completed)
        )
        await asyncio.wait_for(entered.wait(), 1)
        assert active == 4 and not delivered
        release.set()
        brief = await task
        assert maximum == 4 and active == 0
        assert len(brief.market) == 8 and len(brief.sources) == 10
        assert [count for _, count, _ in delivered] == list(range(1, 11))
        assert {total for _, _, total in delivered} == {10}

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("error", "attempts"),
    [
        (RuntimeError("HTTP status 503"), 2),
        (TimeoutError("timed out"), 2),
        (RuntimeError("HTTP status 404"), 1),
        (ValueError("invalid ticker"), 1),
    ],
)
def test_retry_only_transient_market_failures(
    monkeypatch: pytest.MonkeyPatch,
    error: RuntimeError | TimeoutError | ValueError,
    attempts: int,
) -> None:
    """Allow at most two attempts while permanent and validation failures stop."""
    fetch = AsyncMock(side_effect=error)
    monkeypatch.setattr(
        service,
        "create_market_retriever",
        Mock(return_value=Mock(retrieve_range_async=fetch)),
    )
    brief = asyncio.run(
        service.build_brief_async(
            PulseSettings(benchmarks=("SPY",)), include_news=False, now=NOW
        )
    )
    assert fetch.await_count == attempts
    assert brief.sources[0].status == "error"


def test_source_timeout_cancels_underlying_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wait for a pending provider's cleanup before reporting its timeout."""

    async def exercise() -> None:
        """Use a never-completing provider with an observable cleanup path."""
        stopped = asyncio.Event()

        async def retrieve(
            ticker: str, dates: Sequence[date | datetime]
        ) -> list[MarketQuote]:
            """Clean up the request when cancellation reaches the adapter."""
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
            return []

        monkeypatch.setattr(service, "_SOURCE_TIMEOUT", 0.01)
        monkeypatch.setattr(
            service,
            "create_market_retriever",
            Mock(return_value=Mock(retrieve_range_async=retrieve)),
        )
        brief = await service.build_brief_async(
            PulseSettings(benchmarks=("SPY",)), include_news=False, now=NOW
        )
        assert stopped.is_set()
        assert brief.sources[0].status == "error"
        assert "TimeoutError" in brief.sources[0].detail

    asyncio.run(exercise())


def test_cancellation_retains_completed_evidence_and_drains_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deliver finished evidence before cancelling and await pending cleanup."""

    async def exercise() -> None:
        """Finish one symbol while another remains inside its provider request."""
        completed = asyncio.Event()
        pending = asyncio.Event()
        stopped = asyncio.Event()
        results: list[service.SourceResult] = []

        async def retrieve(
            ticker: str, dates: Sequence[date | datetime]
        ) -> list[MarketQuote]:
            """Let FAST finish and make SLOW expose its underlying cancellation."""
            if ticker == "FAST":
                await pending.wait()
                return [_quote()]
            pending.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
            return []

        async def persist(
            result: service.SourceResult, count: int, total: int
        ) -> None:
            """Keep completed evidence independent of final brief creation."""
            results.append(result)
            completed.set()

        monkeypatch.setattr(
            service,
            "create_market_retriever",
            Mock(return_value=Mock(retrieve_range_async=retrieve)),
        )
        task = asyncio.create_task(
            service.build_brief_async(
                PulseSettings(benchmarks=("FAST", "SLOW")),
                include_news=False,
                now=NOW,
                on_source=persist,
            )
        )
        await asyncio.wait_for(completed.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
        assert len(results) == 1 and results[0].market[0].symbol == "FAST"
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(exercise())
