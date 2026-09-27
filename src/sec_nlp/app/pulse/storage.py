# src/sec_nlp/app/pulse/storage.py
"""Persist portable Pulse workspaces, immutable briefs, and research notes.

Configuration is human-editable JSON. Notes and reports are written as new
records rather than overwriting earlier research. Report JSON is published
last so an interrupted export is never mistaken for a complete snapshot.
"""

import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from pydantic import HttpUrl

from sec_nlp.app.pulse.models import (
    Brief,
    Feed,
    JournalEntry,
    PulseSettings,
    Theme,
    WatchItem,
)

logger = logging.getLogger(__name__)


def starter_settings(symbols: tuple[str, ...] = ()) -> PulseSettings:
    """Build an editable profile with primary macro sources and explicit symbols.

    Args:
        symbols: Assets selected by the user; no company holdings are assumed.

    Returns:
        Frozen starter settings with a benchmark and research questions.
    """
    return PulseSettings(
        watchlist=tuple(WatchItem(symbol=symbol) for symbol in symbols),
        themes=(
            Theme(
                name="Rates and policy",
                keywords=(
                    "interest rate",
                    "federal funds",
                    "monetary policy",
                    "FOMC",
                ),
                question="What changed in policy expectations, and which assumptions should I revisit?",
            ),
            Theme(
                name="Inflation and employment",
                keywords=(
                    "inflation",
                    "consumer price",
                    "employment",
                    "payroll",
                    "unemployment",
                ),
                question="Do the releases support or challenge my view of demand and costs?",
            ),
            Theme(
                name="Company developments",
                keywords=(
                    "earnings",
                    "guidance",
                    "acquisition",
                    "capital expenditure",
                    "dividend",
                ),
                question="What should I verify in the company's latest filings?",
            ),
        ),
        feeds=(
            Feed(
                name="Federal Reserve press releases",
                url=HttpUrl(
                    "https://www.federalreserve.gov/feeds/press_all.xml"
                ),
            ),
            Feed(
                name="BLS latest economic indicators",
                url=HttpUrl("https://www.bls.gov/feed/bls_latest.rss"),
            ),
        ),
    )


def _write_new(path: Path, content: str) -> None:
    """Publish a complete UTF-8 file atomically without replacing existing data."""
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, path)
        finally:
            temporary.unlink()


def initialize_workspace(
    workspace: Path,
    settings: PulseSettings | None = None,
) -> Path:
    """Create a workspace configuration without overwriting an existing one.

    Args:
        workspace: Local directory for configuration, notes, and reports.
        settings: Optional explicit profile; otherwise use the macro starter.

    Returns:
        Path to the new editable ``config.json`` file.

    Raises:
        FileExistsError: If the workspace already has a configuration.
        OSError: If the directory or configuration cannot be written.
    """
    profile = settings if settings is not None else starter_settings()
    workspace.mkdir(parents=True, exist_ok=True)
    config_path = workspace / "config.json"
    _write_new(config_path, profile.model_dump_json(indent=2) + "\n")
    return config_path


def load_settings(workspace: Path) -> PulseSettings:
    """Read and validate a workspace's editable profile.

    Raises:
        FileNotFoundError: If ``workspace init`` has not created this workspace.
        ValueError: If configuration does not match the supported schema.
        OSError: If the file cannot be read.
    """
    config_path = workspace / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(
            f"No Pulse config at {config_path}; run sec-nlp workspace init --workspace {workspace}"
        )
    return PulseSettings.model_validate_json(
        config_path.read_text(encoding="utf-8")
    )


def save_note(workspace: Path, entry: JournalEntry) -> Path:
    """Append a journal entry as an immutable individual JSON file.

    Args:
        workspace: Initialized Pulse workspace.
        entry: Validated observation and its research context.

    Returns:
        Path of the newly created journal record.

    Raises:
        FileExistsError: If this entry ID has already been saved.
        ValueError: If the workspace configuration is invalid.
        OSError: If the workspace cannot be read or written.
    """
    load_settings(workspace)
    journal_path = workspace / "journal"
    journal_path.mkdir(exist_ok=True)
    note_path = journal_path / f"{entry.entry_id}.json"
    _write_new(note_path, entry.model_dump_json(indent=2) + "\n")
    return note_path


def load_journal(workspace: Path) -> tuple[JournalEntry, ...]:
    """Return all saved research notes in chronological order.

    Returns:
        Immutable validated records, ordered by creation time and entry ID.

    Raises:
        ValueError: If any journal file has an unsupported or corrupt schema.
        OSError: If a journal file cannot be read.
    """
    entries = []
    for note_path in sorted((workspace / "journal").glob("*.json")):
        try:
            entries.append(
                JournalEntry.model_validate_json(
                    note_path.read_text(encoding="utf-8")
                )
            )
        except ValueError as exc:
            logger.debug("Invalid journal file %s", note_path, exc_info=True)
            raise ValueError(
                f"Invalid journal entry at {note_path}: {exc}"
            ) from exc
    return tuple(
        sorted(entries, key=lambda entry: (entry.created_at, entry.entry_id))
    )


def load_brief(path: Path) -> Brief:
    """Load one saved report for offline rendering or comparison.

    Args:
        path: Report directory or its ``brief.json`` manifest.

    Returns:
        Validated report including its source statuses and original profile.

    Raises:
        ValueError: If the report has an invalid or unsupported schema.
        OSError: If the report cannot be read.
    """
    manifest = path / "brief.json" if path.is_dir() else path
    try:
        return Brief.model_validate_json(manifest.read_text(encoding="utf-8"))
    except ValueError as exc:
        logger.debug("Invalid report file %s", manifest, exc_info=True)
        raise ValueError(f"Invalid Pulse report at {manifest}: {exc}") from exc


def latest_brief(workspace: Path, *, demo: bool = False) -> Brief | None:
    """Find the newest saved report of the requested evidence kind.

    Args:
        workspace: Local Pulse directory.
        demo: Whether to select synthetic reports instead of live reports.

    Returns:
        The newest matching report, or None before the first saved run.

    Raises:
        ValueError: If a saved manifest is corrupt; do not silently skip it.
        OSError: If a report cannot be read.
    """
    reports = (
        load_brief(manifest)
        for manifest in (workspace / "reports").glob("*/brief.json")
    )
    return max(
        (report for report in reports if report.demo == demo),
        key=lambda report: (report.generated_at, report.brief_id),
        default=None,
    )


def save_brief(workspace: Path, brief: Brief) -> Path:
    """Export a unique report directory with JSON and Markdown.

    Args:
        workspace: Initialized local Pulse directory.
        brief: Complete report to persist with immutable evidence.

    Returns:
        Directory containing ``brief.json`` and ``report.md``.

    Raises:
        FileExistsError: If this exact report has already been exported.
        ValueError: If the workspace profile is invalid.
        OSError: If report files cannot be written.
    """
    from sec_nlp.app.pulse.rendering import render_markdown

    load_settings(workspace)
    markdown = render_markdown(brief)
    report_path = (
        workspace
        / "reports"
        / f"{brief.generated_at:%Y%m%dT%H%M%S%f}_{brief.brief_id}"
    )
    report_path.mkdir(parents=True, exist_ok=False)
    _write_new(report_path / "report.md", markdown)
    _write_new(
        report_path / "brief.json", brief.model_dump_json(indent=2) + "\n"
    )
    return report_path


def export_snapshot(workspace: Path, brief: Brief) -> Path:
    """Render saved evidence offline without changing the live report history.

    Args:
        workspace: Directory in which to save a standalone export.
        brief: Previously validated snapshot with its original profile.

    Returns:
        Unique export directory containing the original JSON and new renders.

    Raises:
        OSError: If export files cannot be written.
    """
    from sec_nlp.app.pulse.rendering import render_markdown

    markdown = render_markdown(brief)
    export_path = workspace / "exports" / uuid4().hex
    export_path.mkdir(parents=True, exist_ok=False)
    _write_new(export_path / "report.md", markdown)
    _write_new(
        export_path / "brief.json", brief.model_dump_json(indent=2) + "\n"
    )
    return export_path
