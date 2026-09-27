# tests/tui/test_pulse.py
"""Test cached Pulse navigation, explicit acknowledgement, and authored reviews.

Headless interactions exercise the real shared ledger without allowing provider
requests. Selecting and preparing evidence must preserve its unreviewed state.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import HttpUrl
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Select,
    Static,
    TabbedContent,
    TextArea,
)

from sec_nlp.app.pulse.models import Headline, JournalEntry, WatchItem
from sec_nlp.app.workspace.pulse import pulse_page, review_due
from sec_nlp.app.workspace.pulse_models import PulseFilters
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.tui.app import ResearchWorkspace
from sec_nlp.tui.pulse import PulsePane


def _store(path: Path, *, headlines: int = 3) -> WorkspaceStore:
    """Create relevant cached headlines and an authored thesis without any provider."""
    store = WorkspaceStore(path)
    store.save_settings(
        store.load_settings().model_copy(
            update={
                "watchlist": (
                    WatchItem(
                        symbol="AAPL",
                        name="Apple",
                        aliases=("Apple",),
                        thesis="Watch supplier exposure",
                        invalidation="Persistent margin pressure",
                        review_on=date(2020, 1, 1),
                    ),
                )
            }
        )
    )
    store.save_news(
        tuple(
            Headline(
                title=f"Apple supplier update {number}",
                url=HttpUrl(f"https://example.com/apple/{number}"),
                source="Example News",
                published_at=datetime(2026, 9, 25, tzinfo=UTC),
                symbols=("AAPL",),
            )
            for number in range(headlines)
        )
    )
    return store


def _press(pane: PulsePane, identifier: str) -> None:
    """Dispatch one explicit pane button action through its production handler."""
    pane.press_button(Button.Pressed(pane.query_one(f"#{identifier}", Button)))


def test_hidden_pulse_does_not_read_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defer hidden activity and market projection reads until the Pulse tab opens.

    Args:
        tmp_path: Isolated workspace directory for the test.
        monkeypatch: Scoped replacements for providers or instrumented services.
    """
    activity = Mock(side_effect=AssertionError("Hidden Pulse must stay lazy"))
    overview = Mock(side_effect=AssertionError("Hidden context must stay lazy"))
    monkeypatch.setattr("sec_nlp.tui.pulse.pulse_page", activity)
    monkeypatch.setattr("sec_nlp.tui.pulse.pulse_overview", overview)

    async def scenario() -> None:
        app = ResearchWorkspace(store=_store(tmp_path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            activity.assert_not_called()
            overview.assert_not_called()

    asyncio.run(scenario())


def test_activity_pagination_acknowledgement_and_undo(tmp_path: Path) -> None:
    """Mark only a displayed page and restore that exact batch through Undo."""

    async def scenario() -> None:
        store = _store(tmp_path, headlines=55)
        app = ResearchWorkspace(store=store)
        async with app.run_test(size=(120, 45)) as pilot:
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            await pilot.pause()
            await app.workers.wait_for_complete()
            pane = app.query_one(PulsePane)
            assert pane.query_one("#pulse-activity", DataTable).row_count == 50
            assert pane.page.next_cursor is not None
            _press(pane, "pulse-next")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert len(pane.page.items) == 5
            _press(pane, "pulse-previous")
            await app.workers.wait_for_complete()
            await pilot.pause()
            _press(pane, "pulse-mark-page")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert len(pulse_page(store).items) == 5
            _press(pane, "pulse-undo")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert len(pulse_page(store).items) == 50
            pane.query_one("#pulse-new", Checkbox).value = False
            _press(pane, "pulse-filter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert all(not item.reviewed for item in pane.page.items)
            assert store.list_jobs() == ()

    asyncio.run(scenario())


def test_activity_selection_prefills_without_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep source links through note/research navigation without implicit requests.

    Args:
        tmp_path: Isolated workspace directory for the test.
        monkeypatch: Scoped replacements for providers or instrumented services.
    """
    refresh = AsyncMock(
        side_effect=AssertionError("Navigation must stay offline")
    )
    research = AsyncMock(
        side_effect=AssertionError("Prefilling must not run research")
    )
    browser = Mock()
    monkeypatch.setattr(
        "sec_nlp.app.workspace.service.WorkspaceService.refresh", refresh
    )
    monkeypatch.setattr(
        "sec_nlp.app.workspace.research.execute_research", research
    )
    monkeypatch.setattr("sec_nlp.tui.app.webbrowser.open", browser)

    async def scenario() -> None:
        store = _store(tmp_path)
        app = ResearchWorkspace(store=store)
        async with app.run_test(size=(100, 35)) as pilot:
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            await pilot.pause()
            await app.workers.wait_for_complete()
            pane = app.query_one(PulsePane)
            table = pane.query_one("#pulse-activity", DataTable)
            table.focus()
            await pilot.press("enter")
            item = pane.page.items[0]
            assert not pulse_page(store).items[0].reviewed
            _press(pane, "pulse-research")
            await pilot.pause()
            assert app.query_one("#research-symbols", Input).value == "AAPL"
            assert (
                app.query_one("#research-question", Input).value == item.title
            )
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            _press(pane, "pulse-journal")
            await pilot.pause()
            assert item.url in app.query_one("#observation", TextArea).text
            app._save_note()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert str(store.list_notes()[0].sources[0]) == item.url
            assert len(pulse_page(store).items) == 3
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            await pilot.pause()
            await app.workers.wait_for_complete()
            pane._show_selection(pane.page.items[0])
            _press(pane, "pulse-open")
            await pilot.pause()
            browser.assert_called_once_with(pane.page.items[0].url)
            refresh.assert_not_awaited()
            research.assert_not_awaited()

    asyncio.run(scenario())


def test_watchlist_editor_preserves_history(tmp_path: Path) -> None:
    """Save names, aliases, hypotheses, and dates while retaining removed evidence."""

    async def scenario() -> None:
        store = _store(tmp_path)
        app = ResearchWorkspace(store=store)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            pane = app.query_one(PulsePane)
            pane.query_one(
                "#pulse-tabs", TabbedContent
            ).active = "pulse-watchlist-tab"
            await pilot.pause()
            await app.workers.wait_for_complete()
            for selector, value in (
                ("watch-symbol", "MSFT"),
                ("watch-name", "Microsoft"),
                ("watch-aliases", "Microsoft Corp, Azure"),
                ("watch-thesis", "Watch cloud demand"),
                ("watch-invalidation", "Falling renewals"),
                ("watch-review", "2027-02-01"),
            ):
                pane.query_one(f"#{selector}", Input).value = value
            _press(pane, "watch-save")
            await app.workers.wait_for_complete()
            await pilot.pause()
            saved = store.load_settings().watchlist[-1]
            assert saved.name == "Microsoft"
            assert saved.aliases == ("Microsoft Corp", "Azure")
            assert saved.thesis == "Watch cloud demand"
            assert saved.invalidation == "Falling renewals"
            assert saved.review_on == date(2027, 2, 1)
            pane.query_one("#watch-symbol", Input).value = "AAPL"
            _press(pane, "watch-remove")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert len(store.list_news()) == 3
            assert len(pulse_page(store, PulseFilters(scope="all")).items) == 3
            assert tuple(
                item.symbol for item in store.load_settings().watchlist
            ) == ("MSFT",)

    asyncio.run(scenario())


def test_due_review_completion_and_deferral_keep_original_notes(
    tmp_path: Path,
) -> None:
    """Complete and defer selected due targets using immutable review history."""

    async def scenario() -> None:
        store = _store(tmp_path)
        note = JournalEntry(
            entry_id=uuid4().hex,
            created_at=datetime.now(UTC),
            symbol="AAPL",
            observation="Revisit supplier concentration",
            review_on=date(2020, 1, 1),
        )
        store.save_note(note)
        app = ResearchWorkspace(store=store)
        async with app.run_test(size=(100, 40)) as pilot:
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            pane = app.query_one(PulsePane)
            pane.query_one(
                "#pulse-tabs", TabbedContent
            ).active = "pulse-reviews-tab"
            await pilot.pause()
            await app.workers.wait_for_complete()
            assert len(review_due(store)) == 2
            pane.query_one("#pulse-reviews", DataTable).focus()
            await pilot.press("enter")
            pane.query_one("#pulse-review-note", TextArea).load_text(
                "Reviewed supporting evidence"
            )
            _press(pane, "pulse-review-complete")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert len(review_due(store)) == 1
            pane.query_one("#pulse-reviews", DataTable).focus()
            await pilot.press("enter")
            pane.query_one("#pulse-review-date", Input).value = str(
                datetime.now(UTC).date() + timedelta(days=30)
            )
            _press(pane, "pulse-review-defer")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert review_due(store) == ()
            assert store.list_notes()[0] == note
            assert "deferred" in str(app.query_one("#status", Static).content)

    asyncio.run(scenario())


def test_market_context_shows_retained_quotes_and_failed_attempts(
    tmp_path: Path,
) -> None:
    """Render dated successful observations separately from later provider errors."""
    from sec_nlp.app.pulse.models import MarketObservation, SourceStatus

    async def scenario() -> None:
        store = _store(tmp_path)
        stamp = datetime(2026, 9, 25, tzinfo=UTC)
        store.save_market_observations(
            (
                MarketObservation(
                    symbol="AAPL",
                    quote_date=date(2026, 9, 24),
                    close=123.45,
                    change_1d_pct=1.25,
                    change_5d_pct=-2.5,
                    stale=True,
                    source_url=HttpUrl("https://finance.yahoo.com/quote/AAPL"),
                ),
            ),
            stamp,
        )
        store.save_source_outcome(
            SourceStatus(
                name="AAPL",
                kind="market",
                status="error",
                detail="Source unavailable",
            ),
            stamp + timedelta(days=1),
        )
        app = ResearchWorkspace(store=store)
        async with app.run_test(size=(100, 35)) as pilot:
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            pane = app.query_one(PulsePane)
            pane.query_one(
                "#pulse-tabs", TabbedContent
            ).active = "pulse-market-tab"
            await pilot.pause()
            await app.workers.wait_for_complete()
            table = pane.query_one("#pulse-market", DataTable)
            assert table.row_count == 1
            row = table.get_row_at(0)
            assert row[:5] == ["AAPL", "2026-09-24", "123.45", "1.25", "-2.5"]
            assert "Source unavailable" in str(
                pane.query_one("#pulse-sources", Static).content
            )
            assert "error" in str(
                pane.query_one("#pulse-sources", Static).content
            )

    asyncio.run(scenario())


def test_review_refresh_preserves_selected_target_and_drafts(
    tmp_path: Path,
) -> None:
    """Retain an authored review draft and watchlist edits while cached context reloads."""

    async def scenario() -> None:
        store = _store(tmp_path)
        entry = JournalEntry(
            entry_id=uuid4().hex,
            created_at=datetime.now(UTC),
            observation="Review another issue",
            review_on=date(2020, 1, 2),
        )
        store.save_note(entry)
        app = ResearchWorkspace(store=store)
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            pane = app.query_one(PulsePane)
            pane.query_one(
                "#pulse-tabs", TabbedContent
            ).active = "pulse-reviews-tab"
            await pilot.pause()
            await app.workers.wait_for_complete()
            table = pane.query_one("#pulse-reviews", DataTable)
            table.focus()
            await pilot.press("down", "enter")
            selected = pane._review
            pane.query_one("#pulse-review-note", TextArea).load_text(
                "Unfinished research reasoning"
            )
            pane.query_one(
                "#watch-thesis", Input
            ).value = "Unsaved watchlist reasoning"
            pane.activate(changed=True)
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert pane._review == selected
            assert (
                pane.query_one("#pulse-review-note", TextArea).text
                == "Unfinished research reasoning"
            )
            assert (
                pane.query_one("#watch-thesis", Input).value
                == "Unsaved watchlist reasoning"
            )

    asyncio.run(scenario())


def test_quick_acknowledgements_keep_each_undo_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serialize rapid local mutations instead of cancelling an in-flight database write.

    Args:
        tmp_path: Isolated workspace directory for the test.
        monkeypatch: Scoped replacements for providers or instrumented services.
    """
    import threading

    from sec_nlp.app.workspace.pulse import acknowledge

    started = threading.Event()
    release = threading.Event()
    calls = 0

    def delayed(store: WorkspaceStore, identities: tuple[str, ...]) -> str:
        """Hold the first write until another explicit action has been queued.

        Args:
            store: Workspace receiving the explicit acknowledgements.
            identities: Stable evidence identities captured by the user action.

        Returns:
            The durable undo token produced by the acknowledgement service.
        """
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            assert release.wait(5)
        return acknowledge(store, identities)

    monkeypatch.setattr("sec_nlp.tui.pulse.acknowledge", delayed)

    async def scenario() -> None:
        store = _store(tmp_path)
        app = ResearchWorkspace(store=store)
        async with app.run_test(size=(100, 35)) as pilot:
            app.query_one("#workspace-tabs", TabbedContent).active = "news-tab"
            await pilot.pause()
            await app.workers.wait_for_complete()
            pane = app.query_one(PulsePane)
            first = pane._mark((pane.page.items[0].identity,))
            assert await asyncio.to_thread(started.wait, 5)
            second = pane._mark((pane.page.items[1].identity,))
            release.set()
            await asyncio.gather(first.wait(), second.wait())
            await pilot.pause()
            assert len(pane._undo) == 2
            assert len(pulse_page(store).items) == 1
            await pane._undo_mark().wait()
            await pilot.pause()
            await pane._undo_mark().wait()
            await pilot.pause()
            assert len(pulse_page(store).items) == 3

    asyncio.run(scenario())
