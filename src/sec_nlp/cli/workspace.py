# src/sec_nlp/cli/workspace.py
"""Parse focused commands and render results from shared workspace actions.

This module is imported after top-level dispatch. It keeps parsing and Rich
presentation at the CLI boundary while the application layer owns discovery,
research execution, durable notes, and document caching.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, HttpUrl, TypeAdapter
from rich.console import Console

from sec_nlp.app.pulse.models import JournalEntry, WatchItem
from sec_nlp.app.workspace.models import ScanSpec
from sec_nlp.app.workspace.service import ActionResult, WorkspaceService
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.cli.daily_review import (
    DailyReviewOptions,
    add_pulse_options,
    add_review_options,
    add_watchlist_options,
    edit_watchlist,
    run_review,
    show_pulse,
    show_watchlist,
)
from sec_nlp.cli.tables import (
    filing_table,
    show_inbox,
    show_jobs,
    show_migration,
    show_notes,
    show_scans,
    show_status,
    show_workspace,
)
from sec_nlp.types import ConfigData, JsonDict

if TYPE_CHECKING:
    from _typeshed import SupportsWrite


class RichParser(argparse.ArgumentParser):
    """Render argparse messages through the same Rich console as command output."""

    def _print_message(
        self, message: str, file: SupportsWrite[str] | None = None
    ) -> None:
        """Write parser help and errors without interpreting user text as markup."""
        if message:
            Console(stderr=file is sys.stderr).print(
                message, end="", markup=False, highlight=False
            )


@dataclass
class Options(DailyReviewOptions):
    """Hold typed values populated by the selected argparse command.

    Attributes:
        workspace: Explicit workspace root, or the platform default.
        action: Selected command operation.
        query: User-authored keyword expression or research question.
        name: User-facing scan or workspace label.
        identifier: Saved scan, filing accession, or capability identifier.
        source: Requested source family.
        start: Inclusive historical or query start date.
        end: Inclusive historical or query cutoff.
        filename: Selected manifest document name.
        forms: Exact SEC form filters.
        symbols: Explicit ticker filters or watchlist membership.
        ciks: Explicit SEC entity filters.
        limit: Maximum metadata records requested.
        max_documents: Maximum evidence downloads per scan.
        json_output: Whether to render machine-readable results.
        unread: Whether to filter for unread filings.
        bookmarked: Whether to filter or mark bookmarked evidence.
        contact: Declared SEC contact identity.
        goal: User-authored research objective.
        origin: Legacy workspace to import.
        destination: New report file path.
        export_format: Markdown or JSON export selection.
        observation: User-authored journal observation.
        thesis: Thesis attached to an observation.
        invalidation: Conditions that challenge a thesis.
        review_on: Journal review date.
        symbol: Asset associated with a journal entry.
        sources: Source links attached to a journal entry.
        accession: Filing linked to a journal entry.
        settings: Saved specialist or recipe configuration file.
        sections: Whether to list detected document headings.
        section: Selected document heading or line number.
        find: Local document search phrase.
        raw: Whether to print only unformatted document text.
    """

    workspace: Path | None = None
    action: str = ""
    source: Literal["sec", "news", "market", "all"] = "sec"
    start: date | None = None
    end: date | None = None
    query: str = ""
    name: str = ""
    identifier: str = ""
    filename: str | None = None
    forms: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    ciks: list[str] = field(default_factory=list)
    limit: int = 100
    max_documents: int = 20
    json_output: bool = False
    unread: bool = False
    bookmarked: bool = False
    contact: str | None = None
    goal: str | None = None
    origin: Path | None = None
    destination: Path | None = None
    export_format: str = "markdown"
    observation: str = ""
    thesis: str = ""
    invalidation: str = ""
    review_on: date | None = None
    symbol: str | None = None
    sources: list[str] = field(default_factory=list)
    accession: str | None = None
    settings: Path | None = None
    sections: bool = False
    section: str | None = None
    find: str | None = None
    raw: bool = False


def _query_options(parser: RichParser) -> None:
    """Add the common, bounded search and saved-scan fields."""
    parser.add_argument("--query", default="")
    parser.add_argument("--forms", nargs="*", default=[])
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--ciks", nargs="*", default=[])
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-documents", type=int, default=20)


def _parser(command: str) -> RichParser:
    """Build only the selected command's public interface."""
    parser = RichParser(
        prog=f"sec-nlp {command}", add_help=command != "research"
    )
    parser.add_argument("--workspace", type=Path)
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Render machine-readable JSON.",
    )
    match command:
        case "refresh":
            parser.add_argument(
                "--source",
                choices=("sec", "news", "market", "all"),
                default="sec",
            )
            parser.add_argument(
                "--start",
                type=date.fromisoformat,
                help="Explicit history start date.",
            )
            parser.add_argument("--end", type=date.fromisoformat)
        case "search":
            _query_options(parser)
        case "scan":
            operations = parser.add_subparsers(
                dest="action", required=True, parser_class=RichParser
            )
            saved = operations.add_parser("save")
            saved.add_argument("name")
            _query_options(saved)
            operations.add_parser("list")
            for operation in ("run", "delete"):
                child = operations.add_parser(operation)
                child.add_argument("identifier", help="Saved scan ID or name.")
        case "read":
            parser.add_argument(
                "identifier", help="Accession number in the workspace."
            )
            parser.add_argument(
                "--filename", help="Choose a document from the filing manifest."
            )
            parser.add_argument(
                "--list-documents",
                dest="action",
                action="store_const",
                const="manifest",
            )
            parser.add_argument(
                "--bookmark", action="store_true", dest="bookmarked"
            )
            views = parser.add_mutually_exclusive_group()
            views.add_argument(
                "--sections",
                action="store_true",
                help="List detected evidence headings with line numbers.",
            )
            views.add_argument(
                "--section",
                help="Read a heading or line number from --sections.",
            )
            views.add_argument(
                "--find",
                help="Find literal text in the selected document, with line references.",
            )
            views.add_argument(
                "--raw",
                action="store_true",
                help="Print evidence text only, suitable for shell pipes.",
            )
        case "journal":
            operations = parser.add_subparsers(
                dest="action", required=True, parser_class=RichParser
            )
            note = operations.add_parser("add")
            note.add_argument("observation")
            note.add_argument("--symbol")
            note.add_argument("--accession")
            note.add_argument("--thesis", default="")
            note.add_argument("--invalidation", default="")
            note.add_argument("--review-on", type=date.fromisoformat)
            note.add_argument("--sources", nargs="*", default=[])
            listing = operations.add_parser("list")
            listing.add_argument("--accession")
            add_review_options(operations.add_parser("review"))
        case "export":
            parser.add_argument(
                "--format",
                dest="export_format",
                choices=("markdown", "json"),
                default="markdown",
            )
            parser.add_argument("--destination", type=Path, required=True)
        case "workspace":
            operations = parser.add_subparsers(
                dest="action", required=True, parser_class=RichParser
            )
            initialize = operations.add_parser("init")
            initialize.add_argument("--user-agent", dest="contact")
            initialize.add_argument("--name", default="Research workspace")
            initialize.add_argument("--symbols", nargs="*", default=[])
            configure = operations.add_parser("configure")
            configure.add_argument("--user-agent", dest="contact")
            configure.add_argument("--name", default="")
            configure.add_argument("--goal")
            configure.add_argument("--symbols", nargs="*", default=[])
            operations.add_parser(
                "open",
                help="Print a cached daily overview and return to the shell.",
            )
            operations.add_parser(
                "ui", help="Launch the optional full-screen interface."
            )
            operations.add_parser("status")
            operations.add_parser("jobs")
            add_pulse_options(operations.add_parser("pulse"))
            add_watchlist_options(operations.add_parser("watchlist"))
            inbox = operations.add_parser("inbox")
            inbox.add_argument("--unread", action="store_true")
            inbox.add_argument("--bookmarked", action="store_true")
            inbox.add_argument("--limit", type=int, default=100)
            migrate = operations.add_parser("migrate")
            migrate.add_argument(
                "--from", dest="origin", type=Path, required=True
            )
        case "research":
            parser.add_argument(
                "identifier",
                help="report, analyze, ask, index, retrieve, exb, warranty, financials, holdings, insider, events, recipe",
            )
            parser.add_argument(
                "--settings",
                type=Path,
                help="JSON specialist settings, optionally overridden by CLI flags.",
            )
    return parser


def _global_options_first(arguments: list[str]) -> list[str]:
    """Permit shared workspace/output options before or after subcommands."""
    front: list[str] = []
    rest: list[str] = []
    index = 0
    while index < len(arguments):
        item = arguments[index]
        if item == "--workspace" and index + 1 < len(arguments):
            front.extend(arguments[index : index + 2])
            index += 2
        elif item.startswith("--workspace=") or item == "--json":
            front.append(item)
            index += 1
        else:
            rest.append(item)
            index += 1
    return front + rest


def _scan(options: Options) -> ScanSpec:
    """Validate and freeze the user-selected search window."""
    return ScanSpec(
        name=options.name or options.query or "SEC search",
        query=options.query,
        symbols=tuple(options.symbols),
        ciks=tuple(options.ciks),
        forms=tuple(options.forms),
        start_date=options.start,
        end_date=options.end,
        limit=options.limit,
        max_documents=options.max_documents,
    )


def show_filings(
    store: WorkspaceStore,
    *,
    unread: bool = False,
    bookmarked: bool = False,
    limit: int = 100,
    as_json: bool = False,
) -> None:
    """Render a cached inbox without contacting a provider."""
    items = store.list_filings(
        unread_only=unread, bookmarked_only=bookmarked, limit=limit
    )
    if as_json:
        _show_records(items)
    else:
        show_inbox(items)


def _show_records(records: Sequence[BaseModel]) -> None:
    """Render a single JSON array without terminal-width line wrapping."""
    Console(soft_wrap=True).print(
        "["
        + ",\n".join(record.model_dump_json(indent=2) for record in records)
        + "]",
        markup=False,
        highlight=False,
    )


def _show_action(result: ActionResult, *, as_json: bool) -> int:
    """Render one typed action result and return an informative exit status."""
    console = Console(soft_wrap=True)
    if as_json:
        console.print(
            result.model_dump_json(indent=2), markup=False, highlight=False
        )
    else:
        console.print(result.message, markup=False)
        if result.partial:
            console.print(
                "Coverage is incomplete. Refresh again to continue outstanding discovery.",
                style="yellow",
            )
        for error in result.errors:
            console.print(error, style="yellow", markup=False)
        if result.filings:
            console.print(filing_table(result.filings))
        console.print(
            f"Job: {result.job_id} · Documents cached: {result.documents}",
            markup=False,
            style="dim",
        )
    return 1 if result.errors else 0


def _research(
    store: WorkspaceStore, options: Options, remaining: list[str]
) -> int:
    """Parse only the selected specialist configuration and call the shared action."""
    from sec_nlp.app.workspace.research import (
        execute_research,
        specialist_types,
    )
    from sec_nlp.cli.arguments import _normalize_cli_args
    from sec_nlp.cli.evidence import show_research

    if options.identifier == "recipe":
        from sec_nlp.app.workspace.recipes import load_recipe

        if options.settings is None:
            raise ValueError("research recipe requires --settings PATH")
        payload = TypeAdapter(JsonDict).validate_json(
            load_recipe(options.settings).model_dump_json()
        )
        result = asyncio.run(execute_research(store, "recipe", payload))
        if options.json_output:
            Console(soft_wrap=True).print(
                result.model_dump_json(indent=2), markup=False, highlight=False
            )
        else:
            show_research(result)
        return 0 if result.success else 1
    config_type, _ = specialist_types(options.identifier)
    values = (
        TypeAdapter(JsonDict).validate_json(
            options.settings.read_text(encoding="utf-8")
        )
        if options.settings
        else {}
    )
    normalized = _normalize_cli_args([options.identifier, *remaining])[1:]
    positional: list[str] = []
    while normalized and not normalized[0].startswith("-"):
        positional.append(normalized.pop(0).strip('"'))
    if positional:
        normalized[:0] = ["--symbols", ",".join(positional)]
    if options.identifier == "analyze":
        preset_name = values.get("preset")
        for position, token in enumerate(normalized):
            if token == "--preset" and position + 1 < len(normalized):
                preset_name = normalized[position + 1]
            elif token.startswith("--preset="):
                preset_name = token.split("=", 1)[1]
        if isinstance(preset_name, str):
            from sec_nlp.pipelines.presets.analyze.profiles import (
                AnalyzePreset,
                get_preset_config,
            )

            defaults = TypeAdapter(JsonDict).validate_json(
                TypeAdapter(ConfigData).dump_json(
                    get_preset_config(
                        AnalyzePreset(preset_name.replace("-", "_"))
                    )
                )
            )
            values = {**defaults, **values}
    from pydantic_settings import CliApp, CliSettingsSource

    source = CliSettingsSource(
        config_type,
        cli_prog_name=f"sec-nlp research {options.identifier}",
        cli_kebab_case=True,
        cli_implicit_flags=True,
    )
    configuration = CliApp.run(
        config_type,
        cli_args=normalized,
        cli_settings_source=source,
        cli_cmd_method_name="_configuration_only",
        **values,
    )
    payload = TypeAdapter(JsonDict).validate_json(
        configuration.model_dump_json(exclude_unset=True)
    )
    result = asyncio.run(execute_research(store, options.identifier, payload))
    if options.json_output:
        Console(soft_wrap=True).print(
            result.model_dump_json(indent=2), markup=False, highlight=False
        )
    else:
        show_research(result)
    return 0 if result.success else 1


def run_command(command: str, arguments: list[str]) -> int:
    """Execute a selected CLI command through the shared application layer.

    Args:
        command: Public command selected by the lightweight bootstrap.
        arguments: Arguments following the selected command name.

    Returns:
        Process status; source failures remain visible even when partial evidence exists.
    """
    parser = _parser(command)
    options = Options()
    normalized = _global_options_first(arguments)
    if command == "research" and (
        not normalized or normalized in (["--help"], ["-h"])
    ):
        parser.print_help()
        return 0
    if command == "research":
        _, remaining = parser.parse_known_args(normalized, namespace=options)
    else:
        parser.parse_args(normalized, namespace=options)
        remaining = []
    if command == "research" and options.identifier == "report":
        from sec_nlp.cli.reports import show_report

        report_parser = RichParser(prog="sec-nlp research report")
        report_parser.add_argument(
            "report_path",
            type=Path,
            help="Existing JSON or YAML specialist report.",
        )
        report_arguments = report_parser.parse_args(remaining)
        show_report(report_arguments.report_path, as_json=options.json_output)
        return 0
    if command == "research" and any(
        item in {"--help", "-h"} for item in remaining
    ):
        if options.identifier == "recipe":
            parser.print_help()
        else:
            from pydantic_settings import CliSettingsSource

            from sec_nlp.app.workspace.research import specialist_types

            config_type, _ = specialist_types(options.identifier)
            CliSettingsSource(
                config_type,
                cli_prog_name=f"sec-nlp research {options.identifier}",
                cli_kebab_case=True,
                cli_implicit_flags=True,
                cli_parse_args=["--help"],
            )
        return 0
    if command == "read":
        if (options.find is not None and not options.find.strip()) or (
            options.section is not None and not options.section.strip()
        ):
            parser.error(
                "Document search and section selectors must not be empty"
            )
        if options.json_output and (
            options.raw
            or options.sections
            or options.section is not None
            or options.find is not None
        ):
            parser.error(
                "--json returns the full document; choose a text view without --json"
            )
        if options.action == "manifest" and (
            options.raw
            or options.sections
            or options.section is not None
            or options.find is not None
        ):
            parser.error(
                "--list-documents cannot be combined with document text views"
            )
    if (
        command == "workspace"
        and options.action == "ui"
        and options.json_output
    ):
        parser.error(
            "workspace ui does not produce JSON; use workspace open --json"
        )
    store = WorkspaceStore(options.workspace)
    service = WorkspaceService(store)
    console = Console(soft_wrap=True)
    match command:
        case "refresh":
            source = options.source
            if source not in {"sec", "news", "market", "all"}:
                raise ValueError("Unknown source")
            result = asyncio.run(
                service.refresh(
                    source=source,
                    start_date=options.start,
                    end_date=options.end,
                )
            )
            return _show_action(result, as_json=options.json_output)
        case "search":
            result = asyncio.run(service.search(_scan(options)))
            return _show_action(result, as_json=options.json_output)
        case "scan":
            if options.action == "save":
                spec = _scan(options)
                store.save_scan(spec)
                if options.json_output:
                    console.print(
                        spec.model_dump_json(indent=2),
                        markup=False,
                        highlight=False,
                    )
                else:
                    show_scans((spec,))
            elif options.action == "run":
                return _show_action(
                    asyncio.run(service.run_scan(options.identifier)),
                    as_json=options.json_output,
                )
            elif options.action == "delete":
                matched = next(
                    (
                        item
                        for item in store.list_scans()
                        if options.identifier in {item.scan_id, item.name}
                    ),
                    None,
                )
                if matched is None:
                    raise ValueError("Unknown saved scan")
                store.delete_scan(matched.scan_id)
                if options.json_output:
                    console.print_json(data={"deleted": matched.scan_id})
                else:
                    console.print(f"Deleted scan: {matched.name}", markup=False)
            else:
                if options.json_output:
                    _show_records(store.list_scans())
                else:
                    show_scans(store.list_scans())
        case "read":
            from sec_nlp.cli.evidence import show_document, show_manifest

            if options.bookmarked:
                store.set_bookmarked(options.identifier)
            if options.action == "manifest":
                manifest = asyncio.run(service.manifest(options.identifier))
                if options.json_output:
                    console.print(
                        manifest.model_dump_json(indent=2),
                        markup=False,
                        highlight=False,
                    )
                else:
                    show_manifest(manifest)
            else:
                content = asyncio.run(
                    service.read(options.identifier, filename=options.filename)
                )
                if options.json_output:
                    console.print(
                        content.model_dump_json(indent=2),
                        markup=False,
                        highlight=False,
                    )
                else:
                    from sec_nlp.app.workspace.headlines import (
                        related_headlines,
                    )

                    filing = store.get_filing(options.identifier)
                    headlines = (
                        related_headlines(
                            filing,
                            store.list_news(),
                            store.load_settings().watchlist,
                        )
                        if filing
                        else ()
                    )
                    show_document(
                        content,
                        filing=filing,
                        notes=store.list_notes(
                            accession_number=options.identifier
                        ),
                        headlines=headlines,
                        section=options.section,
                        find=options.find,
                        sections=options.sections,
                        raw=options.raw,
                    )
        case "journal":
            if options.action == "add":
                entry = JournalEntry(
                    entry_id=uuid4().hex,
                    created_at=datetime.now(UTC),
                    symbol=options.symbol,
                    observation=options.observation,
                    thesis=options.thesis,
                    invalidation=options.invalidation,
                    review_on=options.review_on,
                    sources=tuple(HttpUrl(value) for value in options.sources),
                )
                store.save_note(entry, related_accession=options.accession)
                if options.json_output:
                    console.print(
                        entry.model_dump_json(indent=2),
                        markup=False,
                        highlight=False,
                    )
                else:
                    show_notes((entry,))
            elif options.action == "review":
                run_review(store, options, as_json=options.json_output)
            else:
                notes = store.list_notes(accession_number=options.accession)
                if options.json_output:
                    _show_records(notes)
                else:
                    show_notes(notes)
        case "workspace":
            if options.action in {"init", "configure"}:
                profile = store.load_settings()
                values = TypeAdapter(JsonDict).validate_json(
                    profile.model_dump_json()
                )
                if options.contact:
                    values["user_agent"] = options.contact
                if options.name:
                    values["name"] = options.name
                if options.goal:
                    values["goal"] = options.goal
                if options.symbols:
                    existing = {item.symbol: item for item in profile.watchlist}
                    values["watchlist"] = [
                        existing.get(
                            symbol.upper(), WatchItem(symbol=symbol)
                        ).model_dump(mode="json")
                        for symbol in options.symbols
                    ]
                store.save_settings(type(profile).model_validate(values))
                if options.json_output:
                    console.print(
                        store.load_settings().model_dump_json(indent=2),
                        markup=False,
                        highlight=False,
                    )
                else:
                    show_status(store)
            elif options.action == "open":
                if options.json_output:
                    from sec_nlp.app.workspace.pulse import pulse_overview

                    console.print(
                        pulse_overview(store).model_dump_json(indent=2),
                        markup=False,
                        highlight=False,
                    )
                else:
                    show_workspace(store)
            elif options.action == "ui":
                from sec_nlp.tui.app import launch_workspace

                launch_workspace(store.path)
            elif options.action == "migrate":
                from sec_nlp.app.workspace.migrate import migrate_workspace

                if options.origin is None:
                    raise ValueError(
                        "Provide the original workspace with --from"
                    )
                migration = migrate_workspace(options.origin, store)
                if options.json_output:
                    console.print(
                        migration.model_dump_json(indent=2),
                        markup=False,
                        highlight=False,
                    )
                else:
                    show_migration(migration)
            elif options.action == "jobs":
                if options.json_output:
                    _show_records(store.list_jobs())
                else:
                    show_jobs(store.list_jobs())
            elif options.action == "pulse":
                show_pulse(
                    store,
                    options,
                    symbol=options.symbol,
                    as_json=options.json_output,
                )
            elif options.action == "watchlist":
                show_watchlist(
                    edit_watchlist(
                        store,
                        options,
                        symbol=options.symbol,
                        review_on=options.review_on,
                    ),
                    as_json=options.json_output,
                )
            elif options.action == "inbox":
                show_filings(
                    store,
                    unread=options.unread,
                    bookmarked=options.bookmarked,
                    limit=options.limit,
                    as_json=options.json_output,
                )
            else:
                if options.json_output:
                    console.print_json(
                        data={
                            "workspace": str(store.path),
                            "settings": store.load_settings().model_dump(
                                mode="json"
                            ),
                            "checkpoints": [
                                checkpoint.model_dump(mode="json")
                                for checkpoint in store.list_checkpoints()
                            ],
                        }
                    )
                else:
                    show_status(store)
        case "research":
            return _research(store, options, remaining)
        case "export":
            from sec_nlp.app.workspace.export import export_workspace

            if options.destination is None:
                raise ValueError("Choose an export destination")
            path = export_workspace(
                store, options.destination, output_format=options.export_format
            )
            if options.json_output:
                console.print_json(data={"path": str(path)})
            else:
                console.print(f"Exported {path}", markup=False)
    return 0
