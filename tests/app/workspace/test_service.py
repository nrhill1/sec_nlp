# tests/app/workspace/test_service.py
"""Tests for manual discovery progress, bounded catch-up, and cached reading."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import HttpUrl

from sec_nlp.app.pulse.models import PulseSettings
from sec_nlp.app.workspace.models import ScanSpec, SourceCheckpoint
from sec_nlp.app.workspace.service import WorkspaceService
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar import discovery
from sec_nlp.core.edgar.efts import EFTSAPIError, EFTSClient
from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingDocument,
    FilingEntity,
    FilingManifest,
    FilingPage,
    FilingRecord,
    IndexArtifact,
)
from sec_nlp.core.edgar.transport import SecTransport

TODAY = date(2026, 9, 26)


def _filing(number: int = 1, filed: date = TODAY) -> FilingRecord:
    """Build a dated fixture with a source-provided archive identity."""
    accession = f"0001234567-26-{number:06}"
    base = f"https://www.sec.gov/Archives/edgar/data/1234567/{accession.replace('-', '')}/"
    return FilingRecord(
        accession_number=accession,
        entities=(FilingEntity(cik="1234567", name="Example"),),
        form_type="10-K",
        filed_date=filed,
        filing_url=HttpUrl(base + accession + "-index.html"),
        submission_url=HttpUrl(base + accession + ".txt"),
    )


def _daily(published: date) -> IndexArtifact:
    """Describe one explicitly published daily artifact."""
    return IndexArtifact(
        url=HttpUrl(
            f"https://www.sec.gov/Archives/edgar/daily-index/{published.year}/QTR{(published.month - 1) // 3 + 1}/master.{published:%Y%m%d}.idx"
        ),
        year=published.year,
        quarter=(published.month - 1) // 3 + 1,
        kind="daily",
        published_date=published,
    )


@pytest.fixture
def service(tmp_path: Path) -> WorkspaceService:
    """Build an isolated ledger with a valid SEC contact identity."""
    store = WorkspaceStore(tmp_path)
    store.save_settings(PulseSettings(user_agent="Tests test@example.com"))
    return WorkspaceService(store)


async def _indexes(
    service: WorkspaceService,
    start: date | None = None,
    end: date | None = None,
):
    """Run the index coordinator with no real provider calls."""
    async with SecTransport("Tests test@example.com") as transport:
        return await service._refresh_indexes(transport, TODAY, start, end)


@pytest.mark.parametrize("committed", [False, True])
def test_cancelled_feed_retains_partial_checkpoint(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch, committed: bool
) -> None:
    effects = (
        [FilingPage(filings=(_filing(),), next_start=100, raw_entries=100)]
        if committed
        else []
    )
    fetch = AsyncMock(side_effect=[*effects, asyncio.CancelledError()])
    monkeypatch.setattr(discovery, "fetch_latest_filings", fetch)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.refresh(today=TODAY))
    checkpoint = next(
        item
        for item in service.store.list_checkpoints()
        if item.source == "sec-atom"
    )
    assert checkpoint.status == "partial"
    assert checkpoint.pages == int(committed)
    assert len(service.store.list_filings()) == int(committed)
    assert service.store.list_jobs()[0].status == "cancelled"


def test_feed_page_cap_is_visible(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = AsyncMock(
        side_effect=[
            FilingPage(
                filings=(_filing(idx + 1),),
                next_start=(idx + 1) * 100,
                raw_entries=100,
            )
            for idx in range(10)
        ]
    )
    monkeypatch.setattr(discovery, "fetch_latest_filings", fetch)

    async def run():
        async with SecTransport("Tests test@example.com") as transport:
            return await service._refresh_feed(transport)

    filings, partial, errors = asyncio.run(run())
    assert len(filings) == 10 and partial and not errors
    assert fetch.await_count == 10


def test_first_refresh_selects_five_published_dates(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tuple(_daily(TODAY - timedelta(days=idx)) for idx in range(8))
    monkeypatch.setattr(
        discovery, "list_daily_indexes", AsyncMock(return_value=artifacts)
    )

    async def fetch(transport: SecTransport, artifact: IndexArtifact):
        assert artifact.published_date is not None
        return (_filing(artifact.published_date.day, artifact.published_date),)

    fetch_mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(discovery, "fetch_index", fetch_mock)
    filings, partial, errors = asyncio.run(_indexes(service))
    assert len(filings) == 5 and not partial and not errors
    assert min(
        item.filed_date for item in filings if item.filed_date
    ) == TODAY - timedelta(days=4)
    assert fetch_mock.await_count == 5


def test_empty_initial_listing_never_claims_coverage(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        discovery, "list_daily_indexes", AsyncMock(return_value=())
    )
    filings, partial, _ = asyncio.run(_indexes(service))
    assert not filings and partial
    checkpoint = next(
        item
        for item in service.store.list_checkpoints()
        if item.source == "sec-coverage"
    )
    assert checkpoint.status == "partial"


def test_daily_budget_continues_from_committed_dates(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = _daily(date(2026, 8, 31))
    service.store.save_checkpoint(
        SourceCheckpoint(
            source="sec-index",
            scope=str(seed.url),
            artifact_url=str(seed.url),
            cursor="2026-08-31",
            status="complete",
            processed_at=datetime.now(UTC),
        )
    )
    artifacts = tuple(_daily(date(2026, 9, day)) for day in range(1, 26))
    monkeypatch.setattr(
        discovery, "list_daily_indexes", AsyncMock(return_value=artifacts)
    )

    async def fetch(transport: SecTransport, artifact: IndexArtifact):
        assert artifact.published_date is not None
        return (_filing(artifact.published_date.day, artifact.published_date),)

    fetch_mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(discovery, "fetch_index", fetch_mock)
    first, partial, _ = asyncio.run(_indexes(service))
    assert len(first) == 20 and partial and fetch_mock.await_count == 20
    second, partial, _ = asyncio.run(_indexes(service))
    assert len(second) == 5 and not partial and fetch_mock.await_count == 25


def test_failed_earlier_daily_is_retried_before_newer_dates(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    for day, status in [(20, "error"), (23, "complete")]:
        artifact = _daily(date(2026, 9, day))
        service.store.save_checkpoint(
            SourceCheckpoint(
                source="sec-index",
                scope=str(artifact.url),
                artifact_url=str(artifact.url),
                cursor=f"2026-09-{day}",
                status="error" if status == "error" else "complete",
            )
        )
    artifacts = tuple(_daily(date(2026, 9, day)) for day in range(20, 26))
    monkeypatch.setattr(
        discovery, "list_daily_indexes", AsyncMock(return_value=artifacts)
    )
    fetch = AsyncMock(return_value=())
    monkeypatch.setattr(discovery, "fetch_index", fetch)
    _, partial, errors = asyncio.run(_indexes(service))
    assert not partial and not errors
    assert [
        call.args[1].published_date.day for call in fetch.call_args_list
    ] == [20, 21, 22, 24, 25]


def test_weekly_full_reconciles_daily_quarter_with_source_watermark(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    daily = _daily(date(2026, 9, 10))
    old = datetime.now(UTC) - timedelta(days=8)
    service.store.save_checkpoint(
        SourceCheckpoint(
            source="sec-index",
            scope=str(daily.url),
            artifact_url=str(daily.url),
            cursor="2026-09-10",
            status="complete",
            processed_at=old,
        )
    )
    source_filings = (_filing(1, date(2026, 9, 24)),)
    fetch = AsyncMock(return_value=source_filings)
    reconcile = Mock(wraps=service.store.reconcile_index)
    monkeypatch.setattr(discovery, "fetch_index", fetch)
    monkeypatch.setattr(service.store, "reconcile_index", reconcile)
    _, partial, _ = asyncio.run(_indexes(service))
    assert not partial and fetch.call_args.args[1].kind == "full"
    reconcile.assert_called_once()
    checkpoint = reconcile.call_args.args[1]
    assert checkpoint.cursor == "2026-09-24"
    assert reconcile.call_args.args[0] == source_filings


def test_history_boundaries_and_two_full_budget(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed = AsyncMock(
        side_effect=AssertionError("history must not load current feed")
    )
    monkeypatch.setattr(discovery, "fetch_latest_filings", feed)

    async def fetch(transport: SecTransport, artifact: IndexArtifact):
        month = (artifact.quarter - 1) * 3 + 1
        return (
            _filing(month, date(artifact.year, month, 10)),
            _filing(month + 1, date(artifact.year, month, 20)),
        )

    fetch_mock = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(discovery, "fetch_index", fetch_mock)
    reconcile = Mock(
        side_effect=AssertionError("filtered history must not reconcile")
    )
    monkeypatch.setattr(service.store, "reconcile_index", reconcile)
    result = asyncio.run(
        service.refresh(
            today=TODAY, start_date=date(2026, 1, 15), end_date=date(2026, 9, 1)
        )
    )
    assert result.partial and fetch_mock.await_count == 2
    assert all(
        item.filed_date
        and date(2026, 1, 15) <= item.filed_date <= date(2026, 9, 1)
        for item in result.filings
    )
    assert len(result.filings) == 3
    feed.assert_not_awaited()
    reconcile.assert_not_called()


def test_search_merges_duplicate_accession_entities_and_reports_api_error(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    hits = [
        EFTSHit(
            accession_number=_filing().accession_number,
            cik=cik,
            company_name="Example",
            form_type="4",
            filed_date=TODAY,
        )
        for cik in ["1234567", "7654321"]
    ]
    monkeypatch.setattr(EFTSClient, "search_all", AsyncMock(return_value=hits))
    result = asyncio.run(service.search(ScanSpec(name="Owners", query="test")))
    assert len(result.filings) == 1 and len(result.filings[0].entities) == 2
    monkeypatch.setattr(
        EFTSClient,
        "search_all",
        AsyncMock(side_effect=EFTSAPIError(429, "Rate limited")),
    )
    with pytest.raises(RuntimeError, match="SEC search failed: Rate limited"):
        asyncio.run(service.search(ScanSpec(name="Owners", query="test")))
    assert service.store.list_jobs()[0].status == "error"


def test_selected_document_cache_avoids_refetch(
    service: WorkspaceService, monkeypatch: pytest.MonkeyPatch
) -> None:
    filing = _filing()
    service.store.upsert_filings((filing,))
    primary = FilingDocument(
        filename="main.htm",
        sequence=1,
        document_type="10-K",
        url=HttpUrl("https://www.sec.gov/main.htm"),
    )
    exhibit = FilingDocument(
        filename="exhibit.htm",
        sequence=2,
        document_type="EX-10.1",
        url=HttpUrl("https://www.sec.gov/exhibit.htm"),
    )
    manifest = AsyncMock(
        return_value=FilingManifest(filing=filing, documents=(primary, exhibit))
    )
    read = AsyncMock(
        return_value=DocumentContent(document=exhibit, text="Complete exhibit")
    )
    monkeypatch.setattr(discovery, "fetch_filing_manifest", manifest)
    monkeypatch.setattr(discovery, "read_filing_document", read)
    first = asyncio.run(
        service.read(filing.accession_number, filename="exhibit.htm")
    )
    second = asyncio.run(
        service.read(filing.accession_number, filename="exhibit.htm")
    )
    assert first == second and first.document == exhibit
    manifest.assert_awaited_once()
    read.assert_awaited_once()
    assert service.store.list_filings()[0].is_read
