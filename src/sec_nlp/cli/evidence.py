# src/sec_nlp/cli/evidence.py
"""Render source documents and research results as ordinary terminal reports.

Source excerpts, personal notes, and research interpretation have distinct
headings so readers can identify their provenance. Rendering uses literal Rich
text, never opens a window, and does not import or invoke research providers.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.text import Text

from sec_nlp.core.types import is_json_object

if TYPE_CHECKING:
    from sec_nlp.app.pulse.models import Headline, JournalEntry
    from sec_nlp.app.workspace.research import ResearchResult
    from sec_nlp.core.edgar.filing_models import (
        DocumentContent,
        FilingManifest,
        FilingRecord,
    )
    from sec_nlp.types import JsonValue

_SECTION = re.compile(
    r"^\s*(?:ITEM\s+\d+[A-Z]?(?:[.\s:]|$)|PART\s+[IVX]+(?:[.\s:]|$)|CONSOLIDATED\s+)",
    re.IGNORECASE,
)
_MATCH_LIMIT = 50


def _heading(console: Console, label: str) -> None:
    """Separate report sections without entering a fullscreen display."""
    console.print()
    console.rule(Text(label, style="bold cyan"), align="left")


def _fields(console: Console, rows: Sequence[tuple[str, str]]) -> None:
    """Render named metadata without treating values as Rich markup."""
    table = Table.grid(padding=(0, 2), expand=False)
    table.add_column(style="bold", no_wrap=True)
    table.add_column(overflow="fold")
    for label, value in rows:
        table.add_row(Text(label), Text(value))
    console.print(table)


def _provenance(console: Console, filing: FilingRecord) -> None:
    """Display declared filing metadata without inferring an issuer."""
    _fields(
        console,
        (
            ("Accession", filing.accession_number),
            ("Form", filing.form_type),
            ("Filed", str(filing.filed_date or "Not supplied")),
            ("Accepted", str(filing.accepted_at or "Not supplied")),
        ),
    )
    for entity in filing.entities:
        console.print(
            Text(
                f"Entity: {entity.name or 'Unnamed'} · CIK {entity.cik} · Role: {entity.role}"
            )
        )
    console.print(Text(f"Filing source: {filing.filing_url}"), soft_wrap=True)


def show_manifest(
    manifest: FilingManifest, *, console: Console | None = None
) -> None:
    """Show selectable documents with their exact types and source links.

    Args:
        manifest: Source-provided document choices for one filing.
        console: Optional output destination for embedding or tests.
    """
    output = console or Console()
    _heading(output, "Filing documents")
    _provenance(output, manifest.filing)
    table = Table("Seq", "Type", "Filename", "Description", "Bytes")
    for document in manifest.documents:
        table.add_row(
            Text(
                str(document.sequence) if document.sequence is not None else "—"
            ),
            Text(document.document_type or "Not supplied"),
            Text(document.filename),
            Text(document.description or "—"),
            Text(
                f"{document.size_bytes:,}"
                if document.size_bytes is not None
                else "—"
            ),
        )
    output.print(table)
    if not manifest.documents:
        output.print(Text("No documents are listed for this filing."))
    else:
        _heading(output, "Document source links")
        for document in manifest.documents:
            output.print(
                Text(f"{document.filename}: {document.url}"), soft_wrap=True
            )
        output.print(
            Text("Choose a document with read ACCESSION --filename FILENAME.")
        )


def _sections(lines: Sequence[str]) -> tuple[tuple[int, str], ...]:
    """Return one-based line numbers and literal detected filing headings."""
    return tuple(
        (position, line.strip())
        for position, line in enumerate(lines, start=1)
        if _SECTION.match(line)
    )


def _section_bounds(lines: Sequence[str], selection: str) -> tuple[int, int]:
    """Select an exact heading or an unambiguous heading substring.

    Args:
        lines: Source document split into lines.
        selection: Heading text or one-based line number from the section list.

    Returns:
        Zero-based start and exclusive end offsets in the source lines.

    Raises:
        ValueError: If no heading matches or several headings match.
    """
    headings = _sections(lines)
    query = selection.strip().casefold()
    exact = [item for item in headings if item[1].casefold() == query]
    matches = (
        [item for item in headings if item[0] == int(query)]
        if query.isdigit()
        else exact or [item for item in headings if query in item[1].casefold()]
    )
    if not query or not matches:
        raise ValueError(
            "No matching document section. Use --sections to list headings and line numbers."
        )
    if len(matches) > 1:
        positions = ", ".join(str(item[0]) for item in matches)
        raise ValueError(
            f"Several section headings match (lines {positions}). Use --section LINE to choose one."
        )
    start = matches[0][0] - 1
    end = next(
        (line - 1 for line, _ in headings if line - 1 > start), len(lines)
    )
    return start, end


def _show_matches(console: Console, lines: Sequence[str], query: str) -> None:
    """Show bounded literal search excerpts with original source line numbers.

    Args:
        console: Destination for the search report.
        lines: Complete source document lines.
        query: Case-insensitive literal text to locate, never a regex.
    """
    if not query.strip():
        raise ValueError("Search text must not be empty.")
    matches = [
        number
        for number, line in enumerate(lines)
        if query.casefold() in line.casefold()
    ]
    console.print(Text(f"Search: {query}"))
    console.print(Text(f"{len(matches)} matching source lines."))
    if len(matches) > _MATCH_LIMIT:
        console.print(
            Text(
                f"Showing the first {_MATCH_LIMIT} matches; narrow --find for the rest."
            )
        )
    previous = -1
    for position in matches[:_MATCH_LIMIT]:
        start = max(position - 2, previous + 1, 0)
        end = min(position + 3, len(lines))
        if start >= end:
            continue
        if previous >= 0 and start > previous + 1:
            console.print(Text("…"))
        for number in range(start, end):
            marker = (
                ">" if query.casefold() in lines[number].casefold() else " "
            )
            console.print(
                Text(f"{marker} {number + 1:>5}  {lines[number]}"),
                soft_wrap=True,
            )
        previous = end - 1


def _show_notes(console: Console, notes: Sequence[JournalEntry]) -> None:
    """Separate user-authored interpretation from original filing evidence."""
    _heading(console, "Your notes and hypotheses")
    if not notes:
        console.print(Text("No notes are attached to this filing."))
    for number, note in enumerate(notes, start=1):
        console.print(
            Text(
                f"{number}. {note.created_at.isoformat()} · {note.symbol or 'Filing note'} · {note.entry_id}",
                style="bold",
            )
        )
        _fields(console, (("Observation", note.observation),))
        if note.thesis:
            _fields(console, (("Hypothesis", note.thesis),))
        if note.invalidation:
            _fields(console, (("Invalidation", note.invalidation),))
        if note.review_on:
            _fields(console, (("Original review date", str(note.review_on)),))
        for source in note.sources:
            console.print(Text(f"Note source: {source}"), soft_wrap=True)


def _show_headlines(
    console: Console, headlines: Sequence[tuple[Headline, str]]
) -> None:
    """Display cached related coverage with dates, publishers, and match reasons."""
    _heading(console, "Related headlines · cached evidence")
    if not headlines:
        console.print(
            Text("No related headlines are available in the cached selection.")
        )
    for number, (headline, reason) in enumerate(headlines, start=1):
        console.print(Text(f"{number}. {headline.title}", style="bold"))
        _fields(
            console,
            (
                ("Publisher", headline.source),
                ("Published", str(headline.published_at or "Not supplied")),
                ("Match reason", reason),
            ),
        )
        console.print(Text(f"Article source: {headline.url}"), soft_wrap=True)


def show_document(
    content: DocumentContent,
    *,
    filing: FilingRecord | None = None,
    notes: Sequence[JournalEntry] = (),
    headlines: Sequence[tuple[Headline, str]] = (),
    section: str | None = None,
    find: str | None = None,
    sections: bool = False,
    raw: bool = False,
    console: Console | None = None,
) -> None:
    """Show filing evidence and distinguish source text from personal insight.

    Args:
        content: Selected document's complete cached or explicitly fetched text.
        filing: Optional parent filing with declared entities and dates.
        notes: Attached immutable journal entries, supplied from local storage.
        headlines: Cached related headlines paired with relevance explanations.
        section: One detected heading or its one-based line number to display.
        find: Literal case-insensitive search text for numbered excerpts.
        sections: Whether to list detected headings instead of the full text.
        raw: Whether to emit only the document text for shell pipelines.
        console: Optional output destination for embedding or tests.

    Raises:
        ValueError: If selectors conflict, a section is missing or ambiguous,
            or search text is empty.
    """
    if sum((section is not None, find is not None, sections, raw)) > 1:
        raise ValueError(
            "Choose only one of --section, --find, --sections, or --raw."
        )
    output = console or Console()
    if raw:
        output.print(
            Text(content.text),
            soft_wrap=True,
            end="" if content.text.endswith("\n") else "\n",
        )
        return
    lines = content.text.splitlines()
    bounds = _section_bounds(lines, section) if section is not None else None
    if find is not None and not find.strip():
        raise ValueError("Search text must not be empty.")
    _heading(output, "Source and provenance")
    if filing is not None:
        _provenance(output, filing)
    _fields(
        output,
        (
            ("Document", content.document.filename),
            ("Document type", content.document.document_type or "Not supplied"),
            ("Description", content.document.description or "Not supplied"),
        ),
    )
    output.print(
        Text(f"Document source: {content.document.url}"), soft_wrap=True
    )
    _heading(output, "Evidence · document text")
    if sections:
        table = Table("Line", "Detected heading")
        for number, heading in _sections(lines):
            table.add_row(str(number), Text(heading))
        output.print(table)
        output.print(
            Text(
                "Use --section LINE to display a section. Headings are detected from source text."
            )
        )
        if not _sections(lines):
            output.print(
                Text(
                    "No filing section headings were detected; use --find TEXT or read the complete document."
                )
            )
    elif bounds is not None:
        start, end = bounds
        output.print(Text(f"Source lines {start + 1}–{end} of {len(lines)}"))
        output.print(Text("\n".join(lines[start:end])), soft_wrap=True)
    elif find is not None:
        _show_matches(output, lines, find)
    else:
        output.print(
            Text(
                content.text
                or "No readable text is available for this document."
            ),
            soft_wrap=True,
        )
    _show_notes(output, notes)
    _show_headlines(output, headlines)


def _label(name: str) -> str:
    """Turn summary field names into readable labels."""
    return name.replace("_", " ").strip().capitalize()


def _value_text(value: JsonValue) -> str:
    """Describe supplied JSON-compatible values as text rather than JSON syntax."""
    if value is None:
        return "Not supplied"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str | int | float):
        return str(value)
    if is_json_object(value):
        return (
            "\n".join(
                f"{_label(key)}: {_value_text(item)}"
                for key, item in value.items()
            )
            or "None"
        )
    return (
        "\n".join(
            f"{number}. {_value_text(item)}"
            for number, item in enumerate(value, start=1)
        )
        or "None"
    )


def show_research(
    result: ResearchResult, *, console: Console | None = None
) -> None:
    """Separate research interpretation, supplied evidence, and saved artifacts.

    Args:
        result: Shared specialist result with its unchanged compact summary.
        console: Optional output destination for embedding or tests.
    """
    output = console or Console()
    _heading(output, "Research result")
    _fields(
        output,
        (
            ("Capability", result.capability),
            ("Status", "Completed" if result.success else "Failed"),
        ),
    )
    detail = {
        key: value
        for key, value in result.summary.items()
        if key not in {"pipeline", "success", "outputs", "error"}
    }
    evidence_keys = {"evidence", "sources", "source_links", "citations"}
    findings = [
        (key, value)
        for key, value in detail.items()
        if key not in evidence_keys
    ]
    _heading(output, "Findings and interpretation")
    if findings:
        _fields(
            output,
            tuple((_label(key), _value_text(value)) for key, value in findings),
        )
    else:
        output.print(
            Text(
                "This specialist did not supply inline findings. Detailed results remain in its saved artifacts below."
            )
        )
    evidence = [
        (key, value) for key, value in detail.items() if key in evidence_keys
    ]
    if evidence:
        _heading(output, "Supporting evidence and sources")
        _fields(
            output,
            tuple((_label(key), _value_text(value)) for key, value in evidence),
        )
    if result.error:
        _heading(output, "Research error")
        output.print(Text(result.error, style="red"), soft_wrap=True)
    _heading(output, "Saved research artifacts")
    for number, path in enumerate(result.outputs, start=1):
        output.print(Text(f"{number}. {path}"), soft_wrap=True)
    if not result.outputs:
        output.print(Text("No output files were produced."))
    else:
        output.print(
            Text(
                "View a saved JSON/YAML artifact with sec-nlp research report PATH."
            )
        )
