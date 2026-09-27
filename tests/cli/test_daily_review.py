# tests/cli/test_daily_review.py
"""Test scriptable Pulse review state, watchlist edits, and immutable review history."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import HttpUrl

from sec_nlp.app.pulse.models import (
    Headline,
    JournalEntry,
    MarketObservation,
    PulseSettings,
    SourceStatus,
    WatchItem,
)
from sec_nlp.app.workspace.pulse import pulse_page
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


def test_pulse_tables_and_detail_preserve_literal_evidence_without_reviewing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep source labels literal and expose cached evidence without dismissing it."""
    monkeypatch.setenv("COLUMNS", "160")
    store = WorkspaceStore(tmp_path)
    store.save_settings(
        PulseSettings(watchlist=(WatchItem(symbol="AAPL", name="Apple"),))
    )
    store.save_news(
        (
            Headline(
                title="Apple [bold]earnings[/bold]",
                url=HttpUrl("https://example.com/earnings"),
                source="[red]Wire[/red]",
            ),
        )
    )
    initial = pulse_page(store)
    identity = initial.items[0].identity
    shared = ["--workspace", str(tmp_path)]
    assert main(["workspace", "pulse", *shared]) == 0
    output = capsys.readouterr().out
    assert "Evidence · cached Pulse activity" in output
    assert "[bold]earnings[/bold]" in output
    assert "[red]Wire[/red]" in output
    assert "Published/filed: unknown" in output
    assert "Discovered:" in output and "Match:" in output
    assert identity in output and "https://example.com/earnings" in output
    assert main(["workspace", "pulse", "show", identity, *shared]) == 0
    details = capsys.readouterr().out
    assert "Source URL: https://example.com/earnings" in details
    assert "Relevance" in details and "AAPL" in details
    assert "unknown" in details and "new" in details
    assert (
        main(["workspace", "pulse", "show", identity, *shared, "--json"]) == 0
    )
    assert json.loads(capsys.readouterr().out) == initial.items[0].model_dump(
        mode="json"
    )
    assert pulse_page(store) == initial
    assert store.list_jobs() == ()


def test_pulse_overview_separates_market_evidence_from_failed_attempts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Show dated quotes, missing returns, and failed refresh details in separate tables."""
    monkeypatch.setenv("COLUMNS", "160")
    store = WorkspaceStore(tmp_path)
    stamp = datetime(2020, 1, 2, 12, tzinfo=UTC)
    quote = MarketObservation(
        symbol="SPY",
        quote_date=stamp.date(),
        close=300,
        change_1d_pct=1.25,
        source_url=HttpUrl("https://finance.yahoo.com/quote/SPY"),
    )
    store.save_pulse_source(
        SourceStatus(name="SPY", kind="market", status="ok"),
        stamp,
        market=(quote,),
    )
    store.save_source_outcome(
        SourceStatus(
            name="SPY",
            kind="market",
            status="error",
            detail="[red]timeout[/red]",
        ),
        stamp + timedelta(hours=1),
    )
    shared = ["--workspace", str(tmp_path)]
    assert main(["workspace", "pulse", "overview", *shared]) == 0
    output = capsys.readouterr().out
    assert "Evidence · latest successful market observations" in output
    assert "300.00" in output and "+1.25" in output and "2020-01-02" in output
    assert "stale" in output and "5 sessions %" in output and "—" in output
    assert (
        "Latest refresh outcomes" in output and "[red]timeout[/red]" in output
    )
    assert "Research reviews · 0 due" in output
    assert "https://finance.yahoo.com/quote/SPY" in output
    assert main(["workspace", "pulse", "overview", *shared, "--json"]) == 0
    serialized = json.loads(capsys.readouterr().out)
    assert serialized["market"][0]["close"] == 300
    assert serialized["sources"][0]["status"]["status"] == "error"


def test_watchlist_and_review_commands_show_authored_context_and_action_ids(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep research hypotheses literal and use effective schedules in the review queue."""
    monkeypatch.setenv("COLUMNS", "160")
    store = WorkspaceStore(tmp_path)
    today = datetime.now(UTC).date()
    watched = WatchItem(
        symbol="AAPL",
        name="[bold]Apple[/bold]",
        aliases=("Apple Computer",),
        thesis="Demand improves",
        invalidation="Margins fall",
        review_on=today,
    )
    store.save_settings(PulseSettings(watchlist=(watched,)))
    shared = ["--workspace", str(tmp_path)]
    assert main(["workspace", "watchlist", "list", *shared]) == 0
    output = capsys.readouterr().out
    assert "[bold]Apple[/bold]" in output
    assert "Apple Computer" in output and "Demand improves" in output
    assert "Margins fall" in output
    assert main(["workspace", "watchlist", "list", *shared, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        watched.model_dump(mode="json")
    ]
    assert main(["journal", "review", *shared]) == 0
    due = capsys.readouterr().out
    assert "Research reviews · 1 due" in due
    assert "Target: watchlist AAPL" in due and "Margins fall" in due
    assert (
        main(
            [
                "journal",
                "review",
                "complete",
                "watchlist",
                "AAPL",
                "--note",
                "[red]Checked[/red]",
                *shared,
            ]
        )
        == 0
    )
    action = capsys.readouterr().out
    assert "[red]Checked[/red]" in action and "Review ID:" in action
    assert "Next review: Schedule completed" in action
    assert main(["journal", "review", *shared]) == 0
    assert "Research reviews · 0 due" in capsys.readouterr().out
    assert store.load_settings().watchlist == (watched,)
