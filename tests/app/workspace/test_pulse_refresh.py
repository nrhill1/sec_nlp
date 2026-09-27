# tests/app/workspace/test_pulse_refresh.py
"""Tests for streamed Pulse evidence, novelty, and SEC ticker provenance."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from pydantic import HttpUrl

from sec_nlp.app.pulse import service as briefs
from sec_nlp.app.pulse.models import Feed, PulseSettings, WatchItem
from sec_nlp.app.workspace.pulse import pulse_overview
from sec_nlp.app.workspace.service import WorkspaceService
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.transport import SecTransport
from sec_nlp.core.market import MarketQuote
from sec_nlp.core.news.client import NewsItem


def test_streamed_news_keeps_first_discovery_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve first-refresh novelty despite incremental persistence callbacks."""
    store = WorkspaceStore(tmp_path)
    settings = PulseSettings(
        benchmarks=(),
        company_feeds=False,
        feeds=(Feed(name="Example", url=HttpUrl("https://example.com/feed")),),
    )
    store.save_settings(settings)
    fetch = AsyncMock(
        return_value=[
            NewsItem(
                title="Update",
                url="https://example.com/update",
                source="Example",
            )
        ]
    )
    monkeypatch.setattr(
        briefs,
        "create_news_retriever",
        Mock(return_value=Mock(fetch_async=fetch)),
    )
    service = WorkspaceService(store)
    asyncio.run(service.refresh(source="news"))
    first = store.latest_brief(settings)
    assert first is not None and first.headlines[0].is_new
    asyncio.run(service.refresh(source="news"))
    second = store.latest_brief(settings)
    assert second is not None and not second.headlines[0].is_new


def test_cancelled_refresh_keeps_completed_market_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save a successful source before cancellation and record the drained job."""
    store = WorkspaceStore(tmp_path)
    store.save_settings(
        PulseSettings(benchmarks=("FAST", "SLOW"), company_feeds=False)
    )

    async def exercise() -> None:
        """Cancel only after the first source has been durably reported."""
        ready = asyncio.Event()
        stopped = asyncio.Event()
        saved = asyncio.Event()

        async def retrieve(
            ticker: str, dates: Sequence[date | datetime]
        ) -> list[MarketQuote]:
            """Finish one request while preserving a cancellable slow request."""
            if ticker == "FAST":
                await ready.wait()
                return [
                    MarketQuote(
                        timestamp=int(datetime.now(UTC).timestamp()),
                        open_price=99,
                        high=101,
                        low=98,
                        close=100,
                        adjclose=100,
                        volume=5,
                    )
                ]
            ready.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
            return []

        async def progress(event) -> None:
            """Observe the callback only after its database write finished."""
            assert pulse_overview(store).market[0].symbol == "FAST"
            saved.set()

        monkeypatch.setattr(
            briefs,
            "create_market_retriever",
            Mock(return_value=Mock(retrieve_range_async=retrieve)),
        )
        task = asyncio.create_task(
            WorkspaceService(store).refresh(
                source="market", on_progress=progress
            )
        )
        await asyncio.wait_for(saved.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
        assert store.list_jobs()[0].status == "cancelled"
        assert len(pulse_overview(store).market) == 1
        assert not store.list_briefs()

    asyncio.run(exercise())


def test_registry_failure_preserves_stale_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retain declared CIK provenance when a later registry lookup fails."""
    store = WorkspaceStore(tmp_path)
    store.save_settings(
        PulseSettings(
            watchlist=(WatchItem(symbol="ACME"), WatchItem(symbol="BTC-USD")),
            user_agent="Tests test@example.com",
        )
    )

    async def exercise() -> None:
        """Fetch exactly once per mapping refresh on the supplied transport."""
        async with SecTransport(
            "Tests test@example.com", retries=1
        ) as transport:
            fetch = AsyncMock(
                return_value={
                    "0": {"ticker": "ACME", "cik_str": 1234, "title": "Acme"}
                }
            )
            monkeypatch.setattr(transport, "get_json", fetch)
            service = WorkspaceService(store)
            assert await service._refresh_symbol_mappings(transport) is None
            fetch.assert_awaited_once()
            first = pulse_overview(store).mappings
            assert (
                len(first) == 1
                and first[0].cik == "0000001234"
                and not first[0].stale
            )
            fetch.side_effect = httpx.ConnectError("offline")
            assert await service._refresh_symbol_mappings(transport) is not None
            latest = pulse_overview(store).mappings
            assert latest[0].cik == first[0].cik and latest[0].stale
            assert "offline" in latest[0].detail

    asyncio.run(exercise())


def test_first_registry_failure_leaves_durable_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expose a failed first mapping refresh even when no prior mapping exists."""
    store = WorkspaceStore(tmp_path)
    store.save_settings(
        PulseSettings(
            watchlist=(WatchItem(symbol="ACME"),),
            user_agent="Tests test@example.com",
        )
    )

    async def exercise() -> None:
        """Fail the supplied transport without contacting the SEC."""
        async with SecTransport(
            "Tests test@example.com", retries=1
        ) as transport:
            monkeypatch.setattr(
                transport,
                "get_json",
                AsyncMock(
                    side_effect=httpx.ConnectError("registry unavailable")
                ),
            )
            assert await WorkspaceService(store)._refresh_symbol_mappings(
                transport
            )

    asyncio.run(exercise())
    restarted = WorkspaceStore(tmp_path)
    checkpoint = next(
        item
        for item in restarted.list_checkpoints()
        if item.source == "sec-symbol-registry"
    )
    assert checkpoint.status == "error" and checkpoint.last_success_at is None
    assert checkpoint.detail == "registry unavailable"
    assert not pulse_overview(restarted).mappings
