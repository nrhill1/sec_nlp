# tests/cli/test_evidence.py
"""Test literal document evidence, section navigation, and specialist reports."""

import json
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path

import pytest
from pydantic import HttpUrl
from rich.console import Console

from sec_nlp.app.pulse.models import Headline, JournalEntry
from sec_nlp.app.workspace.research import ResearchResult
from sec_nlp.cli.evidence import show_document, show_manifest, show_research
from sec_nlp.cli.reports import show_report
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingDocument,
    FilingEntity,
    FilingManifest,
    FilingRecord,
)


@pytest.fixture
def manifest() -> FilingManifest:
    """Return a filing whose associated owner differs from its accession prefix."""
    filing = FilingRecord(
        accession_number="0001234567-26-000001",
        entities=(
            FilingEntity(
                cik="9999", name="[bold]Example[/bold]", role="reporting owner"
            ),
        ),
        form_type="10-K/A",
        filed_date=date(2026, 9, 27),
        filing_url=HttpUrl("https://www.sec.gov/Archives/example-index.html"),
        submission_url=HttpUrl("https://www.sec.gov/Archives/example.txt"),
    )
    return FilingManifest(
        filing=filing,
        documents=(
            FilingDocument(
                filename="annual.htm",
                url=HttpUrl("https://www.sec.gov/Archives/annual.htm"),
                sequence=1,
                description="Annual report",
                document_type="10-K/A",
                size_bytes=1234,
            ),
            FilingDocument(
                filename="exhibit.htm",
                url=HttpUrl("https://www.sec.gov/Archives/exhibit.htm"),
                sequence=2,
                document_type="EX-10",
            ),
        ),
    )


def _console() -> tuple[Console, StringIO]:
    """Return a narrow terminal capture without color or interactive controls."""
    stream = StringIO()
    return Console(file=stream, width=100, color_system=None), stream


def test_document_distinguishes_source_notes_and_related_news(
    manifest: FilingManifest,
) -> None:
    """Keep literal source content, declared roles, dates, and personal hypotheses."""
    console, stream = _console()
    content = DocumentContent(
        document=manifest.documents[0],
        text="ITEM 1. Business\n[red]Source evidence[/red]",
    )
    note = JournalEntry(
        entry_id="a" * 32,
        created_at=datetime(2026, 9, 27, tzinfo=UTC),
        observation="Personal observation",
        thesis="Unverified hypothesis",
        invalidation="Opposite result",
        review_on=date(2026, 10, 1),
        sources=(HttpUrl("https://example.com/note"),),
    )
    headline = Headline(
        title="[bold]Related story[/bold]",
        source="Example publisher",
        url=HttpUrl("https://example.com/story"),
    )
    show_document(
        content,
        filing=manifest.filing,
        notes=(note,),
        headlines=((headline, "Declared entity match"),),
        console=console,
    )
    rendered = stream.getvalue()
    for fragment in (
        "Source and provenance",
        "Evidence · document text",
        "Your notes and hypotheses",
        "Related headlines · cached evidence",
        "[red]Source evidence[/red]",
        "[bold]Example[/bold]",
        "CIK 0000009999",
        "Role: reporting owner",
        "10-K/A",
        "Document source: https://www.sec.gov/Archives/annual.htm",
        "Hypothesis",
        "Unverified hypothesis",
        "Invalidation",
        "Original review date",
        "https://example.com/note",
        "Example publisher",
        "Published",
        "Not supplied",
        "Declared entity match",
        "https://example.com/story",
    ):
        assert fragment in rendered
    assert "\x1b" not in rendered


def test_manifest_keeps_selectable_files_and_document_sources(
    manifest: FilingManifest,
) -> None:
    """Expose exact document type, declared sequence, filenames, and source URLs."""
    console, stream = _console()
    show_manifest(manifest, console=console)
    rendered = stream.getvalue()
    assert "annual.htm" in rendered and "exhibit.htm" in rendered
    assert "10-K/A" in rendered and "EX-10" in rendered
    assert "1,234" in rendered
    assert "https://www.sec.gov/Archives/exhibit.htm" in rendered


def test_sections_preserve_line_identity_and_reject_ambiguous_headings(
    manifest: FilingManifest,
) -> None:
    """Choose repeated headings by line rather than guessing table-of-contents entries."""
    content = DocumentContent(
        document=manifest.documents[0],
        text="ITEM 1. Business\nContents\nITEM 1. Business\nActual business\nITEM 2. Properties\nProperty evidence",
    )
    console, stream = _console()
    show_document(content, sections=True, console=console)
    assert "Detected heading" in stream.getvalue()
    assert "Actual business" not in stream.getvalue()
    with pytest.raises(ValueError, match="Several section headings match"):
        show_document(content, section="ITEM 1", console=console)
    console, stream = _console()
    show_document(content, section="3", console=console)
    assert "Source lines 3–4" in stream.getvalue()
    assert "Actual business" in stream.getvalue()
    assert "Property evidence" not in stream.getvalue()
    with pytest.raises(ValueError, match="No matching document section"):
        show_document(content, section="Missing", console=console)
    with pytest.raises(ValueError, match="No matching document section"):
        show_document(content, section="2", console=console)


def test_find_is_literal_bounded_and_uses_original_line_numbers(
    manifest: FilingManifest,
) -> None:
    """Treat search input as text and visibly bound a long list of matches."""
    console, stream = _console()
    content = DocumentContent(
        document=manifest.documents[0],
        text="Heading\n"
        + "\n".join(f"[RISK] source {number}" for number in range(60)),
    )
    show_document(content, find="[risk]", console=console)
    rendered = stream.getvalue()
    assert "60 matching source lines" in rendered
    assert "Showing the first 50 matches" in rendered
    assert ">     2  [RISK] source 0" in rendered
    assert "source 59" not in rendered
    with pytest.raises(ValueError, match="must not be empty"):
        show_document(content, find=" ", console=console)


def test_raw_preserves_long_literal_document_text_without_report_sections(
    manifest: FilingManifest,
) -> None:
    """Leave document text suitable for shell pipes without tables or truncation."""
    console, stream = _console()
    source = "[red]Literal[/red] " + "source " * 80 + "\n"
    content = DocumentContent(document=manifest.documents[0], text=source)
    show_document(content, raw=True, console=console)
    assert stream.getvalue() == source
    with pytest.raises(ValueError, match="Choose only one"):
        show_document(content, raw=True, find="source", console=console)


def test_research_status_separates_insight_evidence_errors_and_output_files(
    tmp_path: Path,
) -> None:
    """Show supplied interpretation without pretending to read specialist artifacts."""
    console, stream = _console()
    artifact = tmp_path / "not-read.json"
    result = ResearchResult(
        capability="analyze",
        success=False,
        outputs=(artifact,),
        summary={
            "summary": "[bold]Interpretation[/bold]",
            "confidence": 0,
            "evidence": {
                "quote": "Literal source",
                "url": "https://example.com/evidence",
            },
        },
        error="[red]Provider failed[/red]",
    )
    show_research(result, console=console)
    rendered = stream.getvalue()
    for fragment in (
        "Findings and interpretation",
        "[bold]Interpretation[/bold]",
        "Supporting evidence and sources",
        "Literal source",
        "https://example.com/evidence",
        "Research error",
        "[red]Provider failed[/red]",
        str(artifact),
        "sec-nlp research report PATH",
    ):
        assert fragment in rendered
    assert not artifact.exists()


@pytest.mark.parametrize("extension", ["json", "yaml"])
def test_report_retains_findings_with_their_evidence_and_provenance(
    tmp_path: Path,
    extension: str,
) -> None:
    """Present analyze, exhibit, and warranty record sources under clear headings."""
    payload = {
        "symbol": "ACME",
        "provenance": {"model_name": "Recorded model"},
        "executive_summary": {"key_points": ["Headline insight"]},
        "results": [
            {
                "summary": "[red]Reported finding[/red]",
                "source_excerpt": "Actual filing evidence",
                "source_metadata": {"url": "https://example.com/filing"},
            }
        ],
        "accessions": [
            {
                "accession_number": "0001234567-26-000001",
                "exhibit_details": {
                    "10": {
                        "key_obligations": ["Payment is required"],
                        "sources": ["https://example.com/exhibit"],
                    }
                },
            }
        ],
        "periods": [
            {
                "warranty_liability": 0,
                "warranty_liability_sources": "https://example.com/xbrl",
            }
        ],
    }
    path = tmp_path / f"report.{extension}"
    path.write_text(json.dumps(payload))
    console, stream = _console()
    show_report(path, console=console)
    rendered = stream.getvalue()
    for fragment in (
        "Report provenance",
        "Recorded model",
        "Findings and interpretation",
        "Headline insight",
        "[red]Reported finding[/red]",
        "Evidence and source provenance",
        "Actual filing evidence",
        "https://example.com/filing",
        "Payment is required",
        "https://example.com/exhibit",
        "Warranty liability",
        "https://example.com/xbrl",
    ):
        assert fragment in rendered
    console, stream = _console()
    show_report(path, as_json=True, console=console)
    assert json.loads(stream.getvalue()) == payload


@pytest.mark.parametrize(
    "payload",
    [
        "summary: [unterminated",
        "value: !!python/object/apply:os.system ['false']",
        "value: &self [*self]",
    ],
)
def test_invalid_or_unsafe_yaml_report_fails_clearly(
    tmp_path: Path,
    payload: str,
) -> None:
    """Reject malformed YAML, Python constructors, and recursive aliases."""
    path = tmp_path / "invalid.yaml"
    path.write_text(payload)
    with pytest.raises(ValueError, match="not valid JSON-compatible YAML"):
        show_report(path)


def test_report_bounds_file_reads_and_rejects_unsupported_types(
    tmp_path: Path,
) -> None:
    """Avoid reading oversized artifacts or executing arbitrary report formats."""
    unsupported = tmp_path / "report.py"
    unsupported.write_text("raise RuntimeError('must not run')")
    with pytest.raises(ValueError, match="JSON or YAML"):
        show_report(unsupported)
    with pytest.raises(ValueError, match="not a regular file"):
        show_report(tmp_path / "missing.json")
    oversized = tmp_path / "large.json"
    with oversized.open("wb") as stream:
        stream.truncate(10 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="10 MiB"):
        show_report(oversized)
