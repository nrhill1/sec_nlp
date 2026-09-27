# tests/tui/test_workspace.py
"""Test cached terminal startup, filing reading, notes, and worker cancellation."""

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Static,
    TabbedContent,
    TextArea,
)

from sec_nlp.app.workspace.research import ResearchResult
from sec_nlp.app.workspace.service import ActionResult
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


def test_failed_primary_keeps_document_choices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the new manifest and source visible when its selected document is unreadable."""

    async def scenario() -> None:
        app = ResearchWorkspace(store=_store(tmp_path))
        monkeypatch.setattr(
            app.service,
            "read",
            AsyncMock(side_effect=ValueError("Choose an HTML document")),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            app._source_url = "https://example.com/previous-filing"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert (
                app.query_one("#workspace-tabs", TabbedContent).active
                == "reader-tab"
            )
            assert app.query_one("#reader-text", TextArea).text == ""
            assert "sec.gov/Archives" in app._source_url
            assert "Choose an HTML" in str(
                app.query_one("#status", Static).content
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("visible_symbols", ["", "msft, nvda"])
@pytest.mark.parametrize("explicit_email", [False, True])
def test_research_preserves_advanced_settings_and_shared_contact_handling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    visible_symbols: str,
    explicit_email: bool,
) -> None:
    """Override symbols only when supplied and leave contact defaults to the service."""
    action = AsyncMock(
        return_value=ResearchResult(capability="financials", success=True)
    )
    monkeypatch.setattr(
        "sec_nlp.app.workspace.research.execute_research", action
    )

    async def scenario() -> None:
        store = _store(tmp_path)
        store.save_settings(
            store.load_settings().model_copy(
                update={"user_agent": "Jane Doe <jane@example.com>"}
            )
        )
        app = ResearchWorkspace(store=store)
        async with app.run_test(size=(120, 40)):
            app.query_one("#research-symbols", Input).value = visible_symbols
            app.query_one("#advanced-settings", TextArea).load_text(
                '{"symbols":["AAPL"],"periods":2'
                + (',"email":"explicit@example.com"' if explicit_email else "")
                + "}"
            )
            app.press_button(
                Button.Pressed(app.query_one("#research-run", Button))
            )
            await app.workers.wait_for_complete()
            action.assert_awaited_once()
            values = action.call_args.args[2]
            assert values["symbols"] == (
                ["MSFT", "NVDA"] if visible_symbols else ["AAPL"]
            )
            assert values["periods"] == 2
            if explicit_email:
                assert values["email"] == "explicit@example.com"
            else:
                assert "email" not in values

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "errors", [(), ("0000123456-26-000001: SEC rejected request (403)",)]
)
def test_scan_displays_partial_coverage_and_document_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    errors: tuple[str, ...],
) -> None:
    """Keep discovered evidence visible while reporting incomplete scan results.

    Args:
        tmp_path: Isolated workspace directory for the scan fixture.
        monkeypatch: Scoped replacement of the explicit scan provider action.
        errors: Source failures that must remain visible in terminal status.
    """

    async def scenario() -> None:
        app = ResearchWorkspace(store=_store(tmp_path))
        filing = app.store.list_filings()[0].filing
        monkeypatch.setattr(
            app.service,
            "run_scan",
            AsyncMock(
                return_value=ActionResult(
                    job_id="scan-test",
                    message="Scan found 1 filings; cached 0 documents.",
                    filings=(filing,),
                    partial=True,
                    errors=errors,
                )
            ),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            app._run_scan("saved-scan")
            await app.workers.wait_for_complete()
            await pilot.pause()
            status = str(app.query_one("#status", Static).content)
            assert "partial" in status
            for error in errors:
                assert error in status
            assert app.query_one("#search-results", DataTable).row_count == 1
            assert app.query_one("#inbox", DataTable).row_count == 1

    asyncio.run(scenario())
