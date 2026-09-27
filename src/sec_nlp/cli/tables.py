# src/sec_nlp/cli/tables.py
"""Render workspace records as ordinary terminal tables and readable text.

These views consume cached records and return to the shell without opening a
window, starting a pager, or initiating retrieval. Literal Rich text protects
source content and authored notes from being interpreted as display markup.
"""

from collections.abc import Sequence

from rich.console import Console
from rich.table import Table
from rich.text import Text

from sec_nlp.app.pulse.models import JournalEntry
from sec_nlp.app.workspace.models import (
    InboxItem,
    JobRecord,
    MigrationResult,
    ScanSpec,
)
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.filing_models import FilingRecord


def filing_table(filings: Sequence[FilingRecord]) -> Table:
    """Build a filing table retaining accession identities and declared parties.

    Returns:
        A Rich table with source dates, exact forms, and entity roles.
    """
    table = Table(
        "Filed", "Form", "Declared parties", "Accession", title="Filings"
    )
    for filing in filings:
        table.add_row(
            Text(str(filing.filed_date or "Unknown")),
            Text(filing.form_type),
            Text(
                "\n".join(
                    f"{entity.name or entity.cik} ({entity.role})"
                    for entity in filing.entities
                )
                or "Not supplied"
            ),
            Text(filing.accession_number, overflow="fold"),
        )
    return table


def show_inbox(items: Sequence[InboxItem]) -> None:
    """Print cached filing states alongside their source dates and identities."""
    table = Table(
        "State",
        "Filed",
        "Form",
        "Declared parties",
        "Accession",
        title="Filing inbox",
    )
    for item in items:
        filing = item.filing
        state = ("bookmarked / " if item.bookmarked else "") + (
            "read" if item.is_read else "unread"
        )
        if item.source_withdrawn:
            state += " / withdrawn"
        table.add_row(
            Text(state),
            Text(str(filing.filed_date or "Unknown")),
            Text(filing.form_type),
            Text(
                "\n".join(
                    f"{entity.name or entity.cik} ({entity.role})"
                    for entity in filing.entities
                )
                or "Not supplied"
            ),
            Text(filing.accession_number, overflow="fold"),
        )
    console = Console()
    console.print(table)
    if not items:
        console.print(
            "No cached filings match. Use refresh or search to discover evidence."
        )
    else:
        console.print("Read evidence: sec-nlp read ACCESSION", style="dim")


def show_scans(scans: Sequence[ScanSpec]) -> None:
    """Print saved scan settings and complete identifiers for explicit execution."""
    console = Console()
    table = Table(
        "Name", "Query", "Filters", "Date range", "Limits", title="Saved scans"
    )
    for scan in scans:
        filters = [
            *(f"Form: {value}" for value in scan.forms),
            *(f"Symbol: {value}" for value in scan.symbols),
            *(f"CIK: {value}" for value in scan.ciks),
        ]
        table.add_row(
            Text(scan.name),
            Text(scan.query or "All filings"),
            Text("\n".join(filters) or "None"),
            Text(f"{scan.start_date or 'Any'} → {scan.end_date or 'Any'}"),
            Text(
                f"{scan.limit} filings\n{scan.max_documents} documents\n{'Enabled' if scan.enabled else 'Disabled'}"
            ),
        )
    console.print(table)
    for scan in scans:
        console.print(Text(f"{scan.name}: {scan.scan_id}"), soft_wrap=True)
    if not scans:
        console.print("No saved scans. Use scan save NAME --query TEXT.")


def show_notes(notes: Sequence[JournalEntry]) -> None:
    """Print journal observations with separate thesis, review, and source fields."""
    console = Console()
    console.rule("Journal")
    if not notes:
        console.print("No journal entries match.")
    for entry in notes:
        console.print(
            Text(
                f"{entry.created_at.isoformat()} · {entry.symbol or 'General'}",
                style="bold",
            )
        )
        console.print(Text(f"Entry: {entry.entry_id}"), soft_wrap=True)
        for label, value in (
            ("Observation", entry.observation),
            ("Thesis", entry.thesis),
            ("Invalidation criteria", entry.invalidation),
        ):
            if value:
                console.print(Text(label, style="bold cyan"))
                console.print(Text(value))
        console.print(
            Text(f"Original review date: {entry.review_on or 'Unscheduled'}")
        )
        for source in entry.sources:
            console.print(Text(f"Source: {source}"), soft_wrap=True)
        console.print()
    if notes:
        console.print(
            "Effective due schedule: sec-nlp journal review", style="dim"
        )


def show_jobs(jobs: Sequence[JobRecord]) -> None:
    """Print job outcomes and identifiers without losing source error details."""
    console = Console()
    table = Table("Updated", "Action", "Status", "Details", title="Recent jobs")
    for job in jobs:
        table.add_row(
            Text(job.updated_at.isoformat()),
            Text(job.kind),
            Text(job.status),
            Text(job.message),
        )
    console.print(table)
    for job in jobs:
        console.print(Text(f"{job.kind}: {job.job_id}"), soft_wrap=True)
    if not jobs:
        console.print("No actions have been run in this workspace.")


def show_migration(result: MigrationResult) -> None:
    """Print additive import counts, preserved recipe paths, and warnings."""
    console = Console()
    console.print(Text(f"Imported from: {result.source}"), soft_wrap=True)
    table = Table("Imported records", "Count", title="Workspace migration")
    for label, count in (
        ("Profile", int(result.settings_imported)),
        ("Journal entries", result.notes_imported),
        ("Brief snapshots", result.briefs_imported),
        ("Cache pointers", result.cache_pointers_imported),
        ("Recipes", result.recipes_imported),
        ("Filings", result.filings_imported),
        ("Documents", result.documents_imported),
    ):
        table.add_row(Text(label), Text(str(count)))
    console.print(table)
    for path in result.recipe_paths:
        console.print(Text(f"Recipe: {path}"), soft_wrap=True)
    for warning in result.warnings:
        console.print(Text(warning, style="yellow"))


def show_status(store: WorkspaceStore) -> None:
    """Print profile settings and actual source coverage from the local ledger."""
    console = Console()
    profile = store.load_settings()
    console.rule(Text(profile.name))
    console.print(Text(f"Workspace: {store.path}"), soft_wrap=True)
    console.print(Text(profile.goal))
    profile_table = Table("Setting", "Value", show_header=False)
    for label, value in (
        ("SEC contact", profile.user_agent),
        (
            "Watchlist",
            ", ".join(item.symbol for item in profile.watchlist) or "Empty",
        ),
        ("Benchmarks", ", ".join(profile.benchmarks) or "None"),
        ("Topics", ", ".join(item.name for item in profile.themes) or "None"),
        ("Feeds", ", ".join(item.name for item in profile.feeds) or "None"),
    ):
        profile_table.add_row(Text(label), Text(value))
    console.print(profile_table)
    checkpoints = store.list_checkpoints()
    if checkpoints:
        table = Table(
            "Source / scope",
            "Coverage",
            "Last success",
            "Latest attempt",
            "Details",
            title="Source coverage",
        )
        for checkpoint in checkpoints:
            table.add_row(
                Text(f"{checkpoint.source}\n{checkpoint.scope}"),
                Text(checkpoint.status),
                Text(str(checkpoint.last_success_at or "None")),
                Text(checkpoint.checked_at.isoformat()),
                Text(checkpoint.detail),
            )
        console.print(table)
    else:
        console.print(
            "No source refresh recorded. Refresh runs only when requested."
        )


def show_workspace(store: WorkspaceStore) -> None:
    """Print a bounded cached daily overview and commands for the next action."""
    from sec_nlp.app.workspace.pulse import pulse_overview, pulse_page
    from sec_nlp.cli.daily_tables import show_activity, show_overview

    profile = store.load_settings()
    console = Console()
    console.rule(Text(f"{profile.name} · cached daily overview"))
    console.print(Text(f"Workspace: {store.path}"), soft_wrap=True)
    console.print(Text(profile.goal))
    show_overview(pulse_overview(store), as_json=False)
    show_activity(pulse_page(store))
    console.print(
        "Next: workspace inbox · workspace watchlist · journal review · scan list",
        style="dim",
    )
    console.print(
        "Refresh explicitly: sec-nlp refresh --source all", style="dim"
    )
