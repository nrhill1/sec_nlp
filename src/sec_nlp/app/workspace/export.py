# src/sec_nlp/app/workspace/export.py
"""Export saved workspace evidence without fetching data or generating HTML.

Portable JSON retains typed source records. Markdown provides a readable
research inventory linking filings, headlines, authored notes, and prior briefs.
"""

import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.app.pulse.models import (
    Brief,
    Headline,
    JournalEntry,
    PulseSettings,
)
from sec_nlp.app.workspace.models import (
    InboxItem,
    JobRecord,
    ScanSpec,
    SourceCheckpoint,
)
from sec_nlp.app.workspace.pulse import export_pulse_state
from sec_nlp.app.workspace.pulse_models import PulseState
from sec_nlp.app.workspace.store import WorkspaceStore


class WorkspaceExport(BaseModel):
    """Capture saved evidence and user state in a versioned portable envelope.

    The export carries original timestamps and source URLs and never upgrades
    partial source coverage merely because a report was generated successfully.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[2] = Field(
        default=2, description="Portable workspace export version."
    )
    generated_at: datetime = Field(description="UTC export time.")
    settings: PulseSettings = Field(
        description="User-authored workspace profile."
    )
    filings: tuple[InboxItem, ...] = Field(
        description="Saved filing evidence and review state."
    )
    headlines: tuple[Headline, ...] = Field(
        description="Cached sourced headline evidence."
    )
    notes: tuple[JournalEntry, ...] = Field(
        description="Authored observation history."
    )
    note_links: dict[str, tuple[str, ...]] = Field(
        description="Filing accessions associated with each journal entry."
    )
    scans: tuple[ScanSpec, ...] = Field(
        description="Saved explicit scan definitions."
    )
    coverage: tuple[SourceCheckpoint, ...] = Field(
        description="Source retrieval coverage and failures."
    )
    jobs: tuple[JobRecord, ...] = Field(
        description="Operation outcome history."
    )
    briefs: tuple[Brief, ...] = Field(
        description="Preserved investing snapshots."
    )
    pulse: PulseState = Field(
        description="Activity acknowledgement, review history, and latest provider evidence."
    )


def _plain(value: str) -> str:
    """Escape text that might otherwise become Markdown links or HTML."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def export_workspace(
    store: WorkspaceStore, destination: Path, *, output_format: str = "markdown"
) -> Path:
    """Publish a new offline export without overwriting an existing file.

    Args:
        store: Workspace containing already acquired evidence.
        destination: Explicit output file path.
        output_format: Markdown or JSON serialization.

    Returns:
        The absolute path of the published export.

    Raises:
        ValueError: If the format is unsupported.
        FileExistsError: If the destination already contains a report.
    """
    if output_format not in {"markdown", "json"}:
        raise ValueError("Use markdown or json export format")
    snapshot = WorkspaceExport(
        generated_at=datetime.now(UTC),
        settings=store.load_settings(),
        filings=store.list_filings(limit=None),
        headlines=store.list_news(limit=None),
        notes=store.list_notes(),
        note_links=store.list_note_links(),
        scans=store.list_scans(),
        coverage=store.list_checkpoints(),
        jobs=store.list_jobs(limit=None),
        briefs=store.list_briefs(limit=None),
        pulse=export_pulse_state(store),
    )
    if output_format == "json":
        content = snapshot.model_dump_json(indent=2) + "\n"
    else:
        lines = [
            f"# {_plain(snapshot.settings.name)}",
            "",
            _plain(snapshot.settings.goal),
            "",
            f"Exported {snapshot.generated_at.isoformat()} from saved evidence.",
            "",
            "## Source coverage",
            "",
        ]
        for item in snapshot.coverage:
            lines.append(
                f"- {_plain(item.source)} — {item.status}: {_plain(item.detail)}"
            )
        lines.extend(["", "## Watchlist and market context", ""])
        for watched in snapshot.settings.watchlist:
            lines.append(
                f"- {_plain(watched.symbol)} · {_plain(watched.name)} · Thesis: {_plain(watched.thesis)}"
            )
        current_symbols = {
            *snapshot.settings.benchmarks,
            *(watched.symbol for watched in snapshot.settings.watchlist),
        }
        for quote in snapshot.pulse.market:
            if quote.symbol in current_symbols:
                lines.append(
                    f"- {_plain(quote.symbol)} · {quote.quote_date or 'date unavailable'} · Close: {quote.close} · 1-session change: {quote.change_1d_pct}% · 5-session change: {quote.change_5d_pct}%"
                )
        lines.extend(["", "## Latest source outcomes", ""])
        for outcome in snapshot.pulse.sources:
            lines.append(
                f"- {_plain(outcome.status.name)} · {outcome.status.status} · {outcome.observed_at.isoformat()} · {_plain(outcome.status.detail)}"
            )
        lines.extend(["", "## Pulse review state", ""])
        for activity in snapshot.pulse.activity:
            lines.append(
                f"- {_plain(activity.identity)} · {'reviewed' if activity.reviewed else 'new'} · [{_plain(activity.title)}]({activity.url})"
            )
        lines.extend(["", "## Research review history", ""])
        for review in snapshot.pulse.reviews:
            lines.append(
                f"- {review.created_at.isoformat()} · {review.target_kind} {_plain(review.target_id)} · {review.action} · {_plain(review.note)} · Next: {review.next_review_on or 'unscheduled'}"
            )
        lines.extend(["", "## Filings", ""])
        for item in snapshot.filings:
            filing = item.filing
            company = "; ".join(
                entity.name or entity.cik for entity in filing.entities
            )
            lines.append(
                f"- [{filing.accession_number}]({filing.filing_url}) · {_plain(filing.form_type)} · {filing.filed_date or 'date unavailable'} · {_plain(company)} · {'read' if item.is_read else 'unread'}{' · bookmarked' if item.bookmarked else ''}"
            )
        lines.extend(["", "## Headlines", ""])
        for item in snapshot.headlines:
            lines.append(
                f"- [{_plain(item.title)}]({item.url}) · {_plain(item.source)} · {item.published_at or 'publication date unavailable'} · Matches: {_plain(', '.join((*item.symbols, *item.themes))) or 'configured source'}"
            )
        lines.extend(["", "## Research journal", ""])
        for entry in snapshot.notes:
            lines.extend(
                [
                    f"### {entry.created_at.date()} · {_plain(entry.symbol or 'General')}",
                    "",
                    _plain(entry.observation),
                    "",
                    f"Thesis: {_plain(entry.thesis)}",
                    "",
                    f"Invalidation: {_plain(entry.invalidation)}",
                    "",
                    f"Review: {entry.review_on or 'unscheduled'}",
                    "",
                    "Linked filings: "
                    + ", ".join(snapshot.note_links.get(entry.entry_id, ())),
                    "",
                ]
            )
        lines.extend(["## Saved scans", ""])
        for scan in snapshot.scans:
            lines.append(
                f"- {_plain(scan.name)} · {_plain(scan.query)} · {scan.start_date or 'unbounded'} through {scan.end_date or 'unbounded'}"
            )
        lines.extend(["", "## Specialist outputs", ""])
        for job in snapshot.jobs:
            lines.append(
                f"- {_plain(job.kind)} · {job.status} · {_plain(job.message)}"
            )
        content = "\n".join(lines) + "\n"
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=destination.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination
