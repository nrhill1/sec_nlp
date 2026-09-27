# tests/cli/test_daily_review.py
"""Test scriptable Pulse review state, watchlist edits, and immutable review history."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import HttpUrl

from sec_nlp.app.pulse.models import Headline, JournalEntry, WatchItem
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.cli.__main__ import main


def test_watchlist_edits_preserve_omitted_fields_and_notes(
    tmp_path: Path,
) -> None:
    """Edit a thesis without erasing aliases, then remove only profile membership."""
    shared = ["--workspace", str(tmp_path)]
    assert (
        main(
            [
                "workspace",
                "watchlist",
                "save",
                "aapl",
                *shared,
                "--name",
                "Apple",
                "--aliases",
                "Apple Inc.",
                "--thesis",
                "Original",
                "--invalidation",
                "Lower demand",
                "--review-on",
                "2026-10-15",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "workspace",
                "watchlist",
                "save",
                "AAPL",
                *shared,
                "--thesis",
                "Revised",
            ]
        )
        == 0
    )
    store = WorkspaceStore(tmp_path)
    item = store.load_settings().watchlist[0]
    assert item == WatchItem(
        symbol="AAPL",
        name="Apple",
        aliases=("Apple Inc.",),
        thesis="Revised",
        invalidation="Lower demand",
        review_on=date(2026, 10, 15),
    )
    entry = JournalEntry(
        entry_id="a" * 32,
        created_at=datetime.now(UTC),
        symbol="AAPL",
        observation="Keep evidence",
    )
    store.save_note(entry)
    assert (
        main(
            [
                "workspace",
                "watchlist",
                "save",
                "AAPL",
                *shared,
                "--clear-review",
                "--aliases",
            ]
        )
        == 0
    )
    item = store.load_settings().watchlist[0]
    assert item.review_on is None and item.aliases == ()
    assert main(["workspace", "watchlist", "remove", "AAPL", *shared]) == 0
    assert store.load_settings().watchlist == ()
    assert store.list_notes() == (entry,)
    assert store.list_jobs() == ()


def test_pulse_cli_acknowledges_only_explicit_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep later discoveries new and let an acknowledgement token restore state."""
    store = WorkspaceStore(tmp_path)
    headline = Headline(
        title="First story",
        url=HttpUrl("https://example.com/first"),
        source="Publisher",
    )
    store.save_news((headline,))
    shared = ["--workspace", str(tmp_path)]
    assert (
        main(
            ["workspace", "pulse", "list", "--scope", "all", *shared, "--json"]
        )
        == 0
    )
    page = json.loads(capsys.readouterr().out)
    identity = page["items"][0]["identity"]
    store.save_news(
        (
            Headline(
                title="Later story",
                url=HttpUrl("https://example.com/later"),
                source="Publisher",
            ),
        )
    )
    assert main(["workspace", "pulse", "mark", identity, *shared]) == 0
    token = capsys.readouterr().out.strip()
    assert (
        main(
            ["workspace", "pulse", "list", "--scope", "all", *shared, "--json"]
        )
        == 0
    )
    remaining = json.loads(capsys.readouterr().out)
    assert [item["title"] for item in remaining["items"]] == ["Later story"]
    assert main(["workspace", "pulse", "undo", token, *shared]) == 0
    capsys.readouterr()
    assert (
        main(
            ["workspace", "pulse", "list", "--scope", "all", *shared, "--json"]
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)["items"]) == 2


def test_review_commands_preserve_original_journal_and_export_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Defer and complete an immutable observation through the shared review queue."""
    store = WorkspaceStore(tmp_path)
    today = datetime.now(UTC).date()
    entry = JournalEntry(
        entry_id="b" * 32,
        created_at=datetime.now(UTC),
        observation="Revisit this",
        review_on=today,
    )
    store.save_note(entry)
    shared = ["--workspace", str(tmp_path)]
    assert main(["journal", "review", *shared, "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1
    assert (
        main(
            [
                "journal",
                "review",
                "defer",
                "journal",
                entry.entry_id,
                *shared,
                "--next-review-on",
                str(today + timedelta(days=3)),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["journal", "review", *shared, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert (
        main(
            [
                "journal",
                "review",
                "complete",
                "journal",
                entry.entry_id,
                *shared,
                "--note",
                "Evidence reviewed",
            ]
        )
        == 0
    )
    capsys.readouterr()
    destination = tmp_path / "review.json"
    assert (
        main(
            [
                "export",
                *shared,
                "--format",
                "json",
                "--destination",
                str(destination),
            ]
        )
        == 0
    )
    payload = json.loads(destination.read_text())
    assert payload["schema_version"] == 2
    assert "pulse" in payload
    assert "Evidence reviewed" in destination.read_text()
    assert store.list_notes() == (entry,)
    assert store.list_jobs() == ()


def test_nested_review_help_does_not_initialize_a_workspace(
    tmp_path: Path,
) -> None:
    """Document nested actions without opening the ledger or importing providers."""
    workspace = tmp_path / "absent"
    assert (
        main(
            [
                "workspace",
                "pulse",
                "list",
                "--workspace",
                str(workspace),
                "--help",
            ]
        )
        == 0
    )
    assert not workspace.exists()
    assert (
        main(
            [
                "journal",
                "review",
                "complete",
                "--workspace",
                str(workspace),
                "--help",
            ]
        )
        == 0
    )
    assert not workspace.exists()
