# src/sec_nlp/app/workspace/service.py
"""Coordinate explicit research actions over the persistent workspace ledger.

The terminal and command line share these operations. Provider imports and
network clients are created only when an action is requested. Each action
records partial progress, preserves completed evidence after cancellation,
and returns typed results instead of printing or terminating the process.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.app.workspace.models import JobRecord, ScanSpec, SourceCheckpoint
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingManifest,
    FilingRecord,
    IndexArtifact,
)

if TYPE_CHECKING:
    from sec_nlp.core.edgar.transport import SecTransport

logger = logging.getLogger(__name__)


class ActionResult(BaseModel):
    """Return evidence and visible coverage from an explicit workspace action.

    A partial result remains useful while recording failures or budgets that
    prevent the displayed records from representing complete source coverage.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    job_id: str = Field(
        description="Workspace job associated with this result."
    )
    message: str = Field(description="Readable action outcome.")
    filings: tuple[FilingRecord, ...] = Field(
        default=(), description="Observed filing records."
    )
    documents: int = Field(
        default=0, ge=0, description="Documents downloaded by this action."
    )
    partial: bool = Field(
        default=False,
        description="Whether limits or source failures restricted coverage.",
    )
    errors: tuple[str, ...] = Field(
        default=(), description="Individual source or document failures."
    )


def _quarter(value: date) -> tuple[int, int]:
    """Return the year and SEC calendar quarter for a date."""
    return value.year, (value.month - 1) // 3 + 1


def _quarters(start: date, end: date) -> list[tuple[int, int]]:
    """Return calendar quarters intersecting an inclusive date range."""
    year, quarter = _quarter(start)
    last = _quarter(end)
    result: list[tuple[int, int]] = []
    while (year, quarter) <= last:
        result.append((year, quarter))
        year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
    return result


def _quarter_end(year: int, quarter: int) -> date:
    """Return the last calendar date in a SEC index quarter."""
    following = (
        date(year + 1, 1, 1) if quarter == 4 else date(year, quarter * 3 + 1, 1)
    )
    return following - timedelta(days=1)


class WorkspaceService:
    """Execute user-requested discovery and reading with durable progress.

    The store is the only durable owner; providers return evidence without
    deciding reading state or claiming successful coverage.

    Attributes:
        store: Persistent research workspace shared with the CLI and terminal.
    """

    def __init__(self, store: WorkspaceStore) -> None:
        """Bind actions to an existing workspace without contacting any provider."""
        self.store = store

    def _identity(self) -> str:
        """Require contact information before requesting SEC resources."""
        identity = self.store.load_settings().user_agent
        if "@" not in identity:
            raise ValueError(
                "Set your SEC contact identity first: sec-nlp workspace configure --user-agent 'Your name contact@example.com'"
            )
        return identity

    def _start(self, kind: str, *, scan_id: str | None = None) -> JobRecord:
        """Record an operation only when execution actually begins."""
        job = JobRecord(kind=kind, status="running", scan_id=scan_id)
        self.store.save_job(job)
        return job

    def _finish(
        self,
        job: JobRecord,
        status: Literal["complete", "error", "cancelled"],
        message: str,
    ) -> None:
        """Persist an explicit operation outcome without changing saved evidence."""
        self.store.save_job(
            job.model_copy(
                update={
                    "status": status,
                    "message": message,
                    "updated_at": datetime.now(UTC),
                }
            )
        )

    async def refresh(
        self,
        *,
        source: Literal["sec", "news", "market", "all"] = "sec",
        start_date: date | None = None,
        end_date: date | None = None,
        today: date | None = None,
    ) -> ActionResult:
        """Refresh selected sources only after an explicit user action.

        Args:
            source: Source family to refresh; the default is SEC metadata.
            start_date: Optional earliest date for an explicit historical import.
            end_date: Optional inclusive historical cutoff.
            today: Fixed current date for deterministic callers and tests.

        Returns:
            Available evidence with source errors and partial coverage exposed.
        """
        from sec_nlp.core.edgar.transport import SecTransport

        current = today or datetime.now(UTC).date()
        if start_date and start_date > (end_date or current):
            raise ValueError("History start must not follow its end date")
        identity = self._identity() if source in {"sec", "all"} else ""
        job = self._start(f"refresh:{source}")
        records: dict[str, FilingRecord] = {}
        errors: list[str] = []
        partial = False
        try:
            if source in {"sec", "all"}:
                async with SecTransport(identity) as transport:
                    feed, feed_partial, feed_errors = (
                        await self._refresh_feed(transport)
                        if start_date is None and end_date is None
                        else ((), False, ())
                    )
                    records.update(
                        (item.accession_number, item) for item in feed
                    )
                    (
                        indexed,
                        index_partial,
                        index_errors,
                    ) = await self._refresh_indexes(
                        transport, current, start_date, end_date
                    )
                    records.update(
                        (item.accession_number, item) for item in indexed
                    )
                    partial = feed_partial or index_partial
                    errors.extend((*feed_errors, *index_errors))
            if source in {"news", "market", "all"}:
                from sec_nlp.app.investing.service import build_brief

                brief = await asyncio.to_thread(
                    build_brief,
                    self.store.load_settings(),
                    journal=self.store.list_notes(),
                    include_market=source in {"market", "all"},
                    include_news=source in {"news", "all"},
                )
                self.store.save_brief(brief)
                self.store.save_news(brief.headlines)
                for status in brief.sources:
                    failed = status.status == "error"
                    self.store.save_checkpoint(
                        SourceCheckpoint(
                            source=status.name,
                            scope=source,
                            status="error" if failed else "complete",
                            detail=status.detail,
                        )
                    )
                    if failed:
                        errors.append(f"{status.name}: {status.detail}")
            partial = partial or bool(errors)
            message = f"Observed {len(records)} filings. " + (
                "Coverage is partial; inspect source status and refresh to continue."
                if partial
                else "Requested sources refreshed."
            )
            self._finish(job, "error" if errors else "complete", message)
            return ActionResult(
                job_id=job.job_id,
                message=message,
                filings=self._stored_filings(records),
                partial=partial,
                errors=tuple(errors),
            )
        except asyncio.CancelledError:
            self._finish(
                job,
                "cancelled",
                "Cancelled; committed pages and documents were retained.",
            )
            raise
        except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
            self._finish(job, "error", str(exc))
            raise

    async def _refresh_feed(
        self, transport: SecTransport
    ) -> tuple[tuple[FilingRecord, ...], bool, tuple[str, ...]]:
        """Restart the changing Atom view and commit only fully parsed pages."""
        from sec_nlp.core.edgar.discovery import fetch_latest_filings

        start = 0
        entries = 0
        pages = 0
        seen_pages: set[tuple[str, ...]] = set()
        records: dict[str, FilingRecord] = {}
        error: str | None = None
        partial = False
        prior = next(
            (
                item
                for item in self.store.list_checkpoints()
                if item.source == "sec-atom" and not item.scope
            ),
            None,
        )
        checkpoint = SourceCheckpoint(
            source="sec-atom",
            status="partial",
            last_success_at=prior.last_success_at if prior else None,
            detail="Current feed refresh started; no page committed yet.",
        )
        self.store.save_checkpoint(checkpoint)
        try:
            while entries < 1000 and pages < 10:
                page = await fetch_latest_filings(
                    transport, start=start, count=min(100, 1000 - entries)
                )
                signature = tuple(
                    item.accession_number for item in page.filings
                )
                if signature and signature in seen_pages:
                    partial = True
                    error = "SEC feed repeated a page; historical indexes will reconcile coverage."
                    break
                seen_pages.add(signature)
                pages += 1
                entries += page.raw_entries
                records.update(
                    (item.accession_number, item) for item in page.filings
                )
                checkpoint = checkpoint.model_copy(
                    update={
                        "records": len(records),
                        "pages": pages,
                        "checked_at": datetime.now(UTC),
                        "detail": "Parsed feed page committed; snapshot refresh is still in progress.",
                    }
                )
                self.store.ingest_filings(page.filings, checkpoint)
                if page.next_start is None:
                    partial = not records
                    break
                if page.next_start <= start or page.raw_entries == 0:
                    partial = True
                    error = "SEC feed pagination did not advance."
                    break
                start = page.next_start
                partial = entries >= 1000 or pages >= 10
        except (httpx.HTTPError, ValueError, OSError) as exc:
            logger.debug("SEC live feed failed", exc_info=True)
            error, partial = str(exc), True
        stamp = datetime.now(UTC)
        self.store.save_checkpoint(
            checkpoint.model_copy(
                update={
                    "status": "error"
                    if error
                    else "partial"
                    if partial
                    else "complete",
                    "checked_at": stamp,
                    "last_success_at": checkpoint.last_success_at
                    if partial
                    else stamp,
                    "records": len(records),
                    "pages": pages,
                    "detail": error
                    or (
                        "Empty feed snapshot; no current coverage was established."
                        if not records
                        else "Snapshot page or 1,000-entry limit reached; use index coverage for history."
                        if partial
                        else "Current feed snapshot; not a historical completeness guarantee."
                    ),
                }
            )
        )
        return self._stored_filings(records), partial, (error,) if error else ()

    def _stored_filings(
        self, records: dict[str, FilingRecord]
    ) -> tuple[FilingRecord, ...]:
        """Return one accession with all entity associations committed so far."""
        return tuple(
            self.store.get_filing(accession) or filing
            for accession, filing in records.items()
        )

    async def _refresh_indexes(
        self,
        transport: SecTransport,
        today: date,
        start: date | None,
        end: date | None,
    ) -> tuple[tuple[FilingRecord, ...], bool, tuple[str, ...]]:
        """Reconcile published index artifacts within an explicit request budget."""
        from sec_nlp.core.edgar.discovery import (
            fetch_index,
            full_index_artifact,
            list_daily_indexes,
        )

        checkpoints = self.store.list_checkpoints()
        indexed = {
            (item.source, item.scope): item
            for item in checkpoints
            if item.source in {"sec-index", "sec-history"}
        }
        current_indexes = [
            item for item in indexed.values() if item.source == "sec-index"
        ]
        completed_dates = [
            date.fromisoformat(item.cursor)
            for item in current_indexes
            if item.status == "complete" and item.cursor
        ]
        failed_dates = [
            date.fromisoformat(item.cursor)
            for item in (
                *current_indexes,
                *(
                    item
                    for item in checkpoints
                    if item.source == "sec-index-listing"
                ),
            )
            if item.status != "complete" and item.cursor
        ]
        for item in current_indexes:
            if (
                item.status == "complete"
                or item.cursor
                or not item.artifact_url
            ):
                continue
            match = re.search(
                r"/full-index/(\d{4})/QTR([1-4])/", item.artifact_url
            )
            if match:
                failed_dates.append(
                    date(
                        int(match.group(1)),
                        (int(match.group(2)) - 1) * 3 + 1,
                        1,
                    )
                )
        first_refresh = not current_indexes
        historical = start is not None or end is not None
        cutoff = min(end or today, today)
        anchor = start or (
            cutoff - timedelta(days=30)
            if end is not None
            else (
                min(failed_dates)
                if failed_dates
                else max(completed_dates)
                if completed_dates
                else today - timedelta(days=30)
            )
        )
        quarters = _quarters(anchor, cutoff)
        stamp = datetime.now(UTC)
        quarter_ages: dict[tuple[int, int], datetime] = {}
        full_dates: dict[tuple[int, int], datetime] = {}
        for item in current_indexes:
            if item.status != "complete" or not item.cursor:
                continue
            quarter_key = _quarter(date.fromisoformat(item.cursor))
            processed = item.processed_at or item.checked_at
            quarter_ages[quarter_key] = min(
                processed, quarter_ages.get(quarter_key, processed)
            )
            if item.artifact_url and "/full-index/" in item.artifact_url:
                full_dates[quarter_key] = max(
                    processed, full_dates.get(quarter_key, processed)
                )
        due_quarters = (
            [
                key
                for key, earliest in quarter_ages.items()
                if stamp - full_dates.get(key, earliest) >= timedelta(days=7)
            ]
            if not historical
            else []
        )
        full_mode = historical or len(quarters) > 2 or bool(due_quarters)
        artifacts: list[IndexArtifact] = []
        errors: list[str] = []
        listing_failed = False
        if full_mode:
            requested_quarters = sorted({*quarters, *due_quarters})
            artifacts = [
                full_index_artifact(year=year, quarter=quarter)
                for year, quarter in requested_quarters
            ]
            budget = 2
        else:
            budget = 20
            for year, quarter in quarters:
                listing = SourceCheckpoint(
                    source="sec-index-listing",
                    scope=f"{year}/QTR{quarter}",
                    cursor=max(
                        anchor, date(year, (quarter - 1) * 3 + 1, 1)
                    ).isoformat(),
                    status="partial",
                    detail="Published index listing requested.",
                )
                self.store.save_checkpoint(listing)
                try:
                    published = await list_daily_indexes(
                        transport, year=year, quarter=quarter
                    )
                    artifacts.extend(
                        item
                        for item in published
                        if item.published_date is not None
                        and anchor <= item.published_date <= cutoff
                    )
                    self.store.save_checkpoint(
                        listing.model_copy(
                            update={
                                "status": "complete",
                                "last_success_at": stamp,
                                "records": len(published),
                                "detail": "Published artifact names discovered; individual files require successful import.",
                            }
                        )
                    )
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    logger.debug("SEC index listing failed", exc_info=True)
                    errors.append(f"Index listing {year}/QTR{quarter}: {exc}")
                    listing_failed = True
                    self.store.save_checkpoint(
                        listing.model_copy(
                            update={"status": "error", "detail": str(exc)}
                        )
                    )
            artifacts.sort(key=lambda item: item.published_date or date.min)
            if first_refresh:
                artifacts = artifacts[-5:]
        pending: list[IndexArtifact] = []
        scope_prefix = f"{anchor}:{cutoff}:" if historical else ""
        source_name = "sec-history" if historical else "sec-index"
        for artifact in artifacts:
            previous = indexed.get(
                (source_name, scope_prefix + str(artifact.url))
            )
            if (
                previous is None
                or previous.status != "complete"
                or (
                    artifact.kind == "full"
                    and stamp - (previous.processed_at or previous.checked_at)
                    >= timedelta(days=7)
                )
            ):
                pending.append(artifact)
        partial = (
            len(pending) > budget
            or listing_failed
            or (not artifacts and not completed_dates)
        )
        records: dict[str, FilingRecord] = {}
        coverage = SourceCheckpoint(
            source="sec-coverage",
            status="partial",
            cursor=anchor.isoformat(),
            detail="Index refresh started; coverage is not committed yet.",
        )
        self.store.save_checkpoint(coverage)
        for artifact in pending[:budget]:
            scope = scope_prefix + str(artifact.url)
            previous = indexed.get((source_name, scope))
            checkpoint = SourceCheckpoint(
                source=source_name,
                scope=scope,
                cursor=artifact.published_date.isoformat()
                if artifact.published_date
                else previous.cursor
                if previous
                else None,
                artifact_url=str(artifact.url),
                status="partial",
                last_success_at=previous.last_success_at if previous else None,
                detail="Artifact selected; not yet committed.",
            )
            self.store.save_checkpoint(checkpoint)
            try:
                source_filings = await fetch_index(transport, artifact)
                source_dates = [
                    item.filed_date
                    for item in source_filings
                    if item.filed_date is not None and item.filed_date <= cutoff
                ]
                cursor_date = artifact.published_date or (
                    max(source_dates) if source_dates else None
                )
                filings = (
                    tuple(
                        item
                        for item in source_filings
                        if item.filed_date
                        and anchor <= item.filed_date <= cutoff
                    )
                    if historical
                    else source_filings
                )
                digest = hashlib.sha256(
                    "\n".join(
                        item.model_dump_json() for item in source_filings
                    ).encode()
                ).hexdigest()
                complete = artifact.kind == "daily" or cursor_date is not None
                checkpoint = checkpoint.model_copy(
                    update={
                        "status": "complete" if complete else "partial",
                        "cursor": cursor_date.isoformat()
                        if cursor_date
                        else None,
                        "processed_at": datetime.now(UTC),
                        "last_success_at": datetime.now(UTC)
                        if complete
                        else checkpoint.last_success_at,
                        "content_hash": digest,
                        "records": len(filings),
                        "detail": "Published index parsed and committed."
                        if complete
                        else "Empty full index supplied no dated coverage watermark.",
                    }
                )
                if artifact.kind == "full" and not historical and complete:
                    self.store.reconcile_index(source_filings, checkpoint)
                else:
                    self.store.ingest_filings(filings, checkpoint)
                partial = partial or not complete
                records.update(
                    (item.accession_number, item) for item in filings
                )
            except (httpx.HTTPError, OSError, ValueError) as exc:
                logger.debug("SEC index artifact failed", exc_info=True)
                errors.append(f"{artifact.url}: {exc}")
                self.store.save_checkpoint(
                    checkpoint.model_copy(
                        update={"status": "error", "detail": str(exc)}
                    )
                )
                partial = True
        self.store.save_checkpoint(
            coverage.model_copy(
                update={
                    "status": "partial" if partial else "complete",
                    "detail": f"{min(len(pending), budget)} index artifacts attempted; {max(0, len(pending) - budget)} queued. "
                    + (
                        "No published index coverage was established."
                        if not artifacts and not completed_dates
                        else "First refresh covers up to five published index dates."
                        if first_refresh and not full_mode
                        else "Published artifact coverage; unavailable dates are not assumed empty."
                    ),
                    "records": len(records),
                }
            )
        )
        return self._stored_filings(records), partial, tuple(errors)

    async def search(self, spec: ScanSpec) -> ActionResult:
        """Search retrospective SEC metadata without downloading filing text."""
        from sec_nlp.core.edgar.discovery import filing_from_hit
        from sec_nlp.core.edgar.efts import (
            EFTSAPIError,
            EFTSClient,
            EFTSClientConfig,
        )

        identity = self._identity()
        job = self._start("search", scan_id=spec.scan_id)
        try:
            client = EFTSClient(config=EFTSClientConfig(user_agent=identity))
            hits = await client.search_all(
                spec.query,
                forms=spec.forms,
                ciks=spec.ciks,
                tickers=spec.symbols,
                start_date=spec.start_date,
                end_date=spec.end_date,
                max_results=spec.limit,
            )
            filings = tuple(filing_from_hit(hit) for hit in hits)
            self.store.upsert_filings(filings, source="efts")
            filings = self._stored_filings(
                {item.accession_number: item for item in filings}
            )
            partial = len(hits) >= spec.limit
            message = f"Found {len(filings)} filings." + (
                " Result limit reached; narrow the query or increase the limit."
                if partial
                else ""
            )
            self._finish(job, "complete", message)
            return ActionResult(
                job_id=job.job_id,
                message=message,
                filings=filings,
                partial=partial,
            )
        except asyncio.CancelledError:
            self._finish(job, "cancelled", "Search cancelled.")
            raise
        except EFTSAPIError as exc:
            logger.debug("SEC search failed", exc_info=True)
            self._finish(job, "error", str(exc))
            raise RuntimeError(f"SEC search failed: {exc.message}") from exc
        except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
            self._finish(job, "error", str(exc))
            raise

    async def manifest(self, accession: str) -> FilingManifest:
        """Return a cached manifest or retrieve the selected accession's document list."""
        from sec_nlp.core.edgar.discovery import fetch_filing_manifest
        from sec_nlp.core.edgar.transport import SecTransport

        cached = self.store.get_manifest(accession)
        if cached is not None:
            return cached
        filing = self.store.get_filing(accession)
        if filing is None:
            raise ValueError(
                "Filing is not in this workspace; refresh or search first."
            )
        async with SecTransport(self._identity()) as transport:
            manifest = await fetch_filing_manifest(transport, filing)
        self.store.save_manifest(manifest)
        return manifest

    async def read(
        self,
        accession: str,
        *,
        filename: str | None = None,
        mark_read: bool = True,
    ) -> DocumentContent:
        """Read a selected document from cache or explicitly retrieve it on demand."""
        from sec_nlp.core.edgar.discovery import read_filing_document
        from sec_nlp.core.edgar.transport import SecTransport

        manifest = await self.manifest(accession)
        if filename:
            selected = next(
                (
                    item
                    for item in manifest.documents
                    if item.filename == filename
                ),
                None,
            )
            if selected is None:
                raise ValueError(
                    "Document filename is not in the filing manifest"
                )
        else:
            matching = [
                item
                for item in manifest.documents
                if item.document_type == manifest.filing.form_type
            ]
            candidates = matching or list(manifest.documents)
            if not candidates:
                raise ValueError("The filing has no readable document entries")
            selected = min(
                candidates,
                key=lambda item: (
                    item.sequence if item.sequence is not None else 2**31
                ),
            )
        content = self.store.load_document(selected)
        if content is None:
            async with SecTransport(self._identity()) as transport:
                content = await read_filing_document(transport, selected)
            self.store.cache_document(content)
        if mark_read:
            self.store.set_read(accession)
        return content

    async def run_scan(self, scan_id: str) -> ActionResult:
        """Run a saved query and cache only its bounded selection of documents."""
        spec = next(
            (
                item
                for item in self.store.list_scans()
                if item.scan_id == scan_id or item.name == scan_id
            ),
            None,
        )
        if spec is None:
            raise ValueError("Unknown scan; use scan list to see saved names")
        if not spec.enabled:
            raise ValueError("This scan is disabled; enable it before running")
        job = self._start("scan", scan_id=spec.scan_id)
        downloaded = 0
        errors: list[str] = []
        try:
            results = await self.search(spec)
            for filing in results.filings[: spec.max_documents]:
                try:
                    await self.read(filing.accession_number, mark_read=False)
                    downloaded += 1
                except (
                    httpx.HTTPError,
                    OSError,
                    ValueError,
                    RuntimeError,
                ) as exc:
                    logger.debug("Scan document failed", exc_info=True)
                    errors.append(f"{filing.accession_number}: {exc}")
            message = f"Scan found {len(results.filings)} filings; cached {downloaded} documents."
            result = ActionResult(
                job_id=job.job_id,
                message=message,
                filings=results.filings,
                documents=downloaded,
                partial=results.partial or bool(errors),
                errors=tuple(errors),
            )
            output = self.store.path / "scans" / spec.scan_id
            output.mkdir(parents=True, exist_ok=True)
            payload = output / f"{job.job_id}.json"
            temporary = payload.with_suffix(".tmp")
            temporary.write_text(
                '{"query":'
                + spec.model_dump_json()
                + ',"result":'
                + result.model_dump_json()
                + "}\n",
                encoding="utf-8",
            )
            temporary.replace(payload)
            self._finish(job, "error" if errors else "complete", message)
            return result
        except asyncio.CancelledError:
            self._finish(
                job,
                "cancelled",
                "Scan cancelled; cached evidence remains available.",
            )
            raise
        except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
            self._finish(job, "error", str(exc))
            raise
