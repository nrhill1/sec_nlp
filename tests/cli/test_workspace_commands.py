# tests/cli/test_workspace_commands.py
"""Tests for focused commands, shared-service dispatch, and persistent user state."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sec_nlp.app.investing.models import WatchItem
from sec_nlp.app.workspace.research import ResearchResult
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.cli.__main__ import main


def test_workspace_notes_scans_and_exports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round-trip authored state and a portable JSON export through public commands."""
    workspace = tmp_path / "research"
    shared = ["--workspace", str(workspace)]
    assert (
        main(
            [
                "workspace",
                "init",
                *shared,
                "--symbols",
                "AAPL",
                "--user-agent",
                "Research user@example.com",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "scan",
                "save",
                "Chip supply",
                *shared,
                "--query",
                "semiconductors",
                "--forms",
                "8-K",
                "10-K",
                "--max-documents",
                "3",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "journal",
                "add",
                "Review supplier concentration",
                *shared,
                "--symbol",
                "AAPL",
                "--thesis",
                "Capacity is constrained",
            ]
        )
        == 0
    )
    destination = tmp_path / "export.json"
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
    assert payload["notes"][0]["thesis"] == "Capacity is constrained"
    assert payload["scans"][0]["forms"] == ["8-K", "10-K"]
    assert payload["scans"][0]["max_documents"] == 3
    assert payload["jobs"] == []
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
        == 1
    )
    assert "exists" in capsys.readouterr().err.lower()


def test_watchlist_updates_preserve_theses(tmp_path: Path) -> None:
    """Keep existing research notes when changing the watchlist's membership."""
    store = WorkspaceStore(tmp_path)
    profile = store.load_settings().model_copy(
        update={
            "watchlist": (WatchItem(symbol="AAPL", thesis="Original thesis"),)
        }
    )
    store.save_settings(profile)
    assert (
        main(
            [
                "workspace",
                "configure",
                "--workspace",
                str(tmp_path),
                "--symbols",
                "aapl",
                "MSFT",
            ]
        )
        == 0
    )
    assert store.load_settings().watchlist[0].thesis == "Original thesis"


def test_specialist_flags_use_shared_research_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass explicit CLI overrides to the shared worker without constructing other specialists."""
    worker = AsyncMock(
        return_value=ResearchResult(capability="financials", success=True)
    )
    monkeypatch.setattr(
        "sec_nlp.app.workspace.research.execute_research", worker
    )
    assert (
        main(
            [
                "research",
                "financials",
                "AAPL",
                "MSFT",
                "--periods",
                "2",
                "--workspace",
                str(tmp_path),
            ]
        )
        == 0
    )
    _, capability, settings = worker.call_args.args
    assert capability == "financials"
    assert settings["symbols"] == ["AAPL", "MSFT"]
    assert settings["periods"] == 2
    assert "out_path" not in settings
    assert WorkspaceStore(tmp_path).list_jobs() == ()


def test_research_help_does_not_create_workspace(tmp_path: Path) -> None:
    """Show selected settings without initializing a database or run folder."""
    path = tmp_path / "absent"
    assert (
        main(["research", "financials", "--workspace", str(path), "--help"])
        == 0
    )
    assert not path.exists()


def test_legacy_commands_explain_their_replacements(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Point retired public commands to the supported workspace entry points."""
    assert main(["analyze", "AAPL"]) == 2
    assert "research analyze" in capsys.readouterr().err
