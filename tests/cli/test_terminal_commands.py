# tests/cli/test_terminal_commands.py
"""Test ordinary shell workflows for cached evidence, notes, and saved insight.

These command-level checks exercise the same persisted records as the optional
UI while socket access is disabled. Text rendering must not acknowledge Pulse
activity or silently change original documents.
"""

import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import HttpUrl

from sec_nlp.app.pulse.models import Headline
from sec_nlp.app.workspace.pulse import pulse_page
from sec_nlp.app.workspace.pulse_models import PulseFilters
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.cli.__main__ import main
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingDocument,
    FilingEntity,
    FilingManifest,
    FilingRecord,
)


@pytest.fixture
def cached_filing(
    tmp_path: Path,
) -> tuple[WorkspaceStore, FilingRecord, DocumentContent]:
    """Cache a filing with literal markup, section headings, and related news."""
    store = WorkspaceStore(tmp_path)
    filing = FilingRecord(
        accession_number="0000123456-26-000001",
        entities=(
            FilingEntity(cik="123456", name="Example Inc.", role="issuer"),
        ),
        form_type="10-K",
        filed_date=date(2026, 9, 1),
        filing_url=HttpUrl("https://www.sec.gov/Archives/example-index.html"),
        submission_url=HttpUrl("https://www.sec.gov/Archives/example.txt"),
    )
    document = FilingDocument(
        filename="filing.htm",
        document_type="10-K",
        sequence=1,
        url=HttpUrl("https://www.sec.gov/Archives/filing.htm"),
    )
    content = DocumentContent(
        document=document,
        text="Item 1. Business\nRevenue grew [bold]by ten percent[/bold].\nItem 1A. Risk Factors\nConcentration risk remains.\nItem 10. Directors\nBoard details.\n",
    )
    store.upsert_filings((filing,), source="test")
    store.save_manifest(FilingManifest(filing=filing, documents=(document,)))
    store.cache_document(content)
    store.save_news(
        (
            Headline(
                title="Example expands capacity",
                url=HttpUrl("https://example.com/story"),
                source="Test publisher",
            ),
        )
    )
    return store, filing, content


def test_reader_notes_and_insight_stay_accessible_in_shell(
    cached_filing: tuple[WorkspaceStore, FilingRecord, DocumentContent],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Read source evidence, add a note, and inspect it without a window or network."""
    store, filing, content = cached_filing
    shared = ["--workspace", str(store.path)]
    assert (
        main(
            [
                "journal",
                "add",
                "Check concentration",
                "--accession",
                filing.accession_number,
                "--thesis",
                "Demand may persist",
                *shared,
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["read", filing.accession_number, *shared]) == 0
    output = capsys.readouterr().out
    for value in (
        "Evidence",
        "Source",
        "filing.htm",
        "[bold]by ten percent[/bold]",
        "Check concentration",
        "Demand may persist",
        "Test publisher",
        "https://example.com/story",
    ):
        assert value in output
    assert store.load_document(content.document) == content
    assert all(
        not item.reviewed
        for item in pulse_page(store, PulseFilters(scope="all")).items
    )
    assert store.list_jobs() == ()


def test_document_modes_and_json_preserve_complete_source(
    cached_filing: tuple[WorkspaceStore, FilingRecord, DocumentContent],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Expose sections, local search, full raw text, and original structured content."""
    store, filing, content = cached_filing
    base = ["read", filing.accession_number, "--workspace", str(store.path)]
    assert main([*base, "--sections"]) == 0
    assert "Risk Factors" in capsys.readouterr().out
    assert main([*base, "--section", "1"]) == 0
    selected = capsys.readouterr().out
    assert "Revenue grew" in selected and "Board details" not in selected
    assert main([*base, "--find", "concentration"]) == 0
    assert "Concentration risk remains." in capsys.readouterr().out
    assert main([*base, "--raw"]) == 0
    assert capsys.readouterr().out.rstrip("\n") == content.text.rstrip("\n")
    assert main([*base, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == content.model_dump(
        mode="json"
    )
    assert main([*base, "--list-documents", "--json"]) == 0
    assert (
        json.loads(capsys.readouterr().out)["documents"][0]["filename"]
        == "filing.htm"
    )
    assert (
        main(["workspace", "inbox", "--workspace", str(store.path), "--json"])
        == 0
    )
    assert (
        json.loads(capsys.readouterr().out)[0]["filing"]["accession_number"]
        == filing.accession_number
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--raw", "--section", "1"],
        ["--find", ""],
        ["--section", " "],
        ["--json", "--sections"],
        ["--list-documents", "--raw"],
    ],
)
def test_conflicting_document_views_fail_before_workspace_creation(
    tmp_path: Path, arguments: list[str]
) -> None:
    """Reject incompatible presentation options before fetching or marking evidence."""
    workspace = tmp_path / "absent"
    assert (
        main(
            [
                "read",
                "0000123456-26-000001",
                "--workspace",
                str(workspace),
                *arguments,
            ]
        )
        == 2
    )
    assert not workspace.exists()


def test_report_command_is_local_and_preserves_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inspect saved findings without initializing a workspace or loading specialists."""
    path = tmp_path / "analysis.json"
    payload = {
        "executive_summary": {"key_points": ["Demand grew"]},
        "results": [
            {
                "summary": "More capacity",
                "source_excerpt": "Planned capacity increases",
                "source_url": "https://example.com/evidence",
            }
        ],
    }
    path.write_text(json.dumps(payload))
    workspace = tmp_path / "absent"
    base = ["research", "report", str(path), "--workspace", str(workspace)]
    assert main(base) == 0
    output = capsys.readouterr().out
    assert "Demand grew" in output and "Planned capacity increases" in output
    assert "https://example.com/evidence" in output
    assert main([*base, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == payload
    assert not workspace.exists()


def test_fullscreen_interface_requires_explicit_ui_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve the existing interface behind an explicit optional launch command."""
    launch = Mock()
    monkeypatch.setattr("sec_nlp.tui.app.launch_workspace", launch)
    assert main(["workspace", "open", "--workspace", str(tmp_path)]) == 0
    launch.assert_not_called()
    assert main(["workspace", "ui", "--workspace", str(tmp_path)]) == 0
    launch.assert_called_once_with(tmp_path)
