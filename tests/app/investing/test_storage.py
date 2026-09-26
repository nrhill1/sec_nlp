# tests/app/investing/test_storage.py
"""Tests for investing profile validation and immutable local research storage."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from sec_nlp.app.investing.models import (
    Brief,
    InvestingSettings,
    JournalEntry,
    WatchItem,
)
from sec_nlp.app.investing.storage import (
    export_snapshot,
    initialize_workspace,
    latest_brief,
    load_brief,
    load_journal,
    load_settings,
    save_brief,
    save_note,
    starter_settings,
)


def test_initialize_preserves_existing_config_and_empty_watchlist(
    tmp_path: Path,
) -> None:
    """Keep initialization offline and refuse to overwrite a research profile."""
    config_path = initialize_workspace(tmp_path)
    before = config_path.read_text()
    assert load_settings(tmp_path).watchlist == ()
    assert len(load_settings(tmp_path).feeds) == 2
    with pytest.raises(FileExistsError):
        initialize_workspace(tmp_path, InvestingSettings(name="Replacement"))
    assert config_path.read_text() == before


def test_starter_normalizes_explicit_symbols() -> None:
    """Retain macro sources when the user selects a watchlist."""
    settings = starter_settings(("aapl", "BRK-B"))
    assert tuple(item.symbol for item in settings.watchlist) == (
        "AAPL",
        "BRK-B",
    )
    assert settings.feeds
    assert settings.themes


@pytest.mark.parametrize(
    "symbol", ("../notes", "$(whoami)", "AAPL;exit", "", "AAPL MSFT")
)
def test_unsafe_or_empty_symbols_are_rejected(symbol: str) -> None:
    """Reject symbols that would be ambiguous in files or follow-up commands."""
    with pytest.raises(ValidationError):
        WatchItem(symbol=symbol)


def test_duplicate_symbols_and_unknown_config_keys_are_rejected() -> None:
    """Reject ambiguous profiles and misspelled configuration fields."""
    with pytest.raises(ValidationError, match="Duplicate watchlist symbol"):
        starter_settings(("AAPL", "aapl"))
    with pytest.raises(ValidationError, match="extra_forbidden"):
        InvestingSettings.model_validate_json('{"lookbak_days": 7}')


def test_notes_round_trip_without_overwrite(tmp_path: Path) -> None:
    """Preserve each note's timestamp, evidence, and original wording."""
    initialize_workspace(tmp_path)
    entry = JournalEntry(
        entry_id="a" * 32,
        created_at=datetime(2026, 9, 26, tzinfo=UTC),
        observation="Check guidance",
        symbol="aapl",
    )
    path = save_note(tmp_path, entry)
    assert load_journal(tmp_path) == (entry,)
    with pytest.raises(FileExistsError):
        save_note(tmp_path, entry.model_copy(update={"observation": "Changed"}))
    assert JournalEntry.model_validate_json(path.read_text()) == entry


def test_corrupt_journal_identifies_file(tmp_path: Path) -> None:
    """Surface corrupt research history rather than silently omitting a note."""
    notes = tmp_path / "journal"
    notes.mkdir()
    (notes / "broken.json").write_text("{")
    with pytest.raises(ValueError, match="broken.json"):
        load_journal(tmp_path)


def test_missing_profile_and_unsupported_schema_are_actionable(
    tmp_path: Path,
) -> None:
    """Report missing initialization and reject unknown report versions."""
    with pytest.raises(FileNotFoundError, match="invest init"):
        load_settings(tmp_path)
    path = tmp_path / "brief.json"
    path.write_text('{"schema_version": 2}')
    with pytest.raises(ValueError, match="Invalid investing report"):
        load_brief(path)


def test_reports_round_trip_and_demo_never_becomes_live_baseline(
    tmp_path: Path,
) -> None:
    """Select live history independently of newer synthetic reports."""
    settings = starter_settings()
    initialize_workspace(tmp_path, settings)
    live = Brief(
        brief_id="b" * 32,
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        settings=settings,
    )
    demo = Brief(
        brief_id="c" * 32,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        settings=settings,
        demo=True,
    )
    path = save_brief(tmp_path, live)
    save_brief(tmp_path, demo)
    assert {file.name for file in path.iterdir()} == {
        "report.md",
        "brief.json",
    }
    assert load_brief(path) == live
    assert latest_brief(tmp_path) == live
    assert latest_brief(tmp_path, demo=True) == demo
    with pytest.raises(FileExistsError):
        save_brief(tmp_path, live)


def test_snapshot_replay_uses_original_profile_without_modifying_history(
    tmp_path: Path,
) -> None:
    """Render offline even if current profile is absent or invalid."""
    brief = Brief(
        brief_id="d" * 32,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        settings=starter_settings(),
    )
    (tmp_path / "config.json").write_text("invalid")
    first = export_snapshot(tmp_path, brief)
    second = export_snapshot(tmp_path, brief)
    assert first != second
    assert load_brief(first) == brief
    assert (second / "report.md").is_file()
    assert latest_brief(tmp_path) is None


def test_incomplete_export_is_not_a_report(tmp_path: Path) -> None:
    """Ignore interrupted directories whose JSON manifest was not published."""
    incomplete = tmp_path / "reports" / "unfinished"
    incomplete.mkdir(parents=True)
    (incomplete / "report.md").write_text("partial")
    assert latest_brief(tmp_path) is None
