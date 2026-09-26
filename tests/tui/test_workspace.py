# tests/tui/test_workspace.py
"""Test cached terminal startup, filing reading, notes, and worker cancellation."""

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl
from textual.widgets import DataTable, Input, Static, TabbedContent, TextArea

from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingDocument,
    FilingEntity,
    FilingManifest,
    FilingRecord,
)
from sec_nlp.tui.app import ResearchWorkspace


def _store(path: Path) -> WorkspaceStore:
    """Create saved filing evidence that can be read without any network calls."""
    store = WorkspaceStore(path)
    filing = FilingRecord(
        accession_number="0000123456-26-000001",
        entities=(
            FilingEntity(cik="123456", name="Example Company", role="issuer"),
        ),
        form_type="10-K",
        filed_date=date(2026, 9, 24),
        filing_url=HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/123456/000012345626000001/example-index.html"
        ),
        submission_url=HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/123456/0000123456-26-000001.txt"
        ),
    )
    document = FilingDocument(
        filename="annual.html",
        url=HttpUrl(
            "https://www.sec.gov/Archives/edgar/data/123456/000012345626000001/annual.html"
        ),
        sequence=1,
        document_type="10-K",
    )
    store.upsert_filings((filing,))
    store.save_manifest(FilingManifest(filing=filing, documents=(document,)))
    store.cache_document(
        DocumentContent(
            document=document,
            text="ITEM 1. Business\nCompany evidence\nITEM 1A. Risks\nSupply chain risk",
            html="<p>Original source</p>",
        )
    )
    return store


def test_mount_reads_cached_inbox_without_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep both full-sized and compact startup entirely offline."""
    refresh = AsyncMock(side_effect=AssertionError("Startup must not refresh"))
    monkeypatch.setattr(
        "sec_nlp.app.workspace.service.WorkspaceService.refresh", refresh
    )

    async def scenario() -> None:
        for size in ((120, 40), (80, 24)):
            app = ResearchWorkspace(store=_store(tmp_path))
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                assert app.query_one("#inbox", DataTable).row_count == 1
                assert app.store.list_jobs() == ()
        refresh.assert_not_awaited()

    asyncio.run(scenario())


def test_keyboard_reader_and_local_search(tmp_path: Path) -> None:
    """Read cached evidence, preserve provenance, and find a passage by keyboard."""

    async def scenario() -> None:
        app = ResearchWorkspace(store=_store(tmp_path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert (
                app.query_one("#workspace-tabs", TabbedContent).active
                == "reader-tab"
            )
            assert (
                "Supply chain risk"
                in app.query_one("#reader-text", TextArea).text
            )
            assert app.store.list_filings()[0].is_read
            app.query_one("#reader-find", Input).value = "risk"
            app._find_next()
            assert (
                app.query_one("#reader-text", TextArea).cursor_location[0] >= 2
            )

    asyncio.run(scenario())


def test_journal_note_links_selected_filing(tmp_path: Path) -> None:
    """Keep authored notes linked to selected evidence and visible after reload."""

    async def scenario() -> None:
        app = ResearchWorkspace(store=_store(tmp_path))
        async with app.run_test(size=(120, 40)) as pilot:
            app.accession = "0000123456-26-000001"
            app.query_one(
                "#workspace-tabs", TabbedContent
            ).active = "journal-tab"
            app.query_one("#observation", TextArea).load_text(
                "Check the supplier concentration note."
            )
            app._save_note()
            await pilot.pause()
            assert (
                len(app.store.list_notes(accession_number=app.accession)) == 1
            )

    asyncio.run(scenario())


def test_cancel_worker_keeps_workspace_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop explicit pending work without losing access to saved evidence."""

    async def scenario() -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def pending(*args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(
            "sec_nlp.app.workspace.service.WorkspaceService.refresh", pending
        )
        app = ResearchWorkspace(store=_store(tmp_path))
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_refresh()
            await started.wait()
            await pilot.press("escape")
            await asyncio.wait_for(cancelled.wait(), 2)
            await pilot.pause()
            assert app.query_one("#inbox", DataTable).row_count == 1
            assert "Cancelled" in str(app.query_one("#status", Static).render())

    asyncio.run(scenario())
