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
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import HttpUrl, TypeAdapter
from rich.console import Console
from rich.table import Table

from sec_nlp.app.investing.models import JournalEntry, WatchItem
from sec_nlp.app.workspace.models import ScanSpec
from sec_nlp.app.workspace.service import ActionResult, WorkspaceService
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.types import JsonDict

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
class Options(argparse.Namespace):
    """Hold typed values populated by the selected argparse command.

    Attributes:
        workspace: Explicit workspace root, or the platform default.
        action: Selected command operation.
        query: User-authored keyword expression or research question.
        name: User-facing scan or workspace label.
        identifier: Saved scan, filing accession, or capability identifier.
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
            operations.add_parser("review")
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
            operations.add_parser("open")
            operations.add_parser("status")
            operations.add_parser("jobs")
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
                help="analyze, ask, index, retrieve, exb, warranty, financials, holdings, insider, events, recipe",
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
) -> None:
    """Render a cached inbox without contacting a provider."""
    table = Table("State", "Filed", "Form", "Company", "Accession")
    for item in store.list_filings(
        unread_only=unread, bookmarked_only=bookmarked, limit=limit
    ):
        filing = item.filing
        state = ("★ " if item.bookmarked else "") + (
            "read" if item.is_read else "new"
        )
        company = "; ".join(
            entity.name or entity.cik for entity in filing.entities
        )
        table.add_row(
            state,
            str(filing.filed_date or "—"),
            filing.form_type,
            company,
            filing.accession_number,
        )
    Console().print(table)


def _show_action(result: ActionResult, *, as_json: bool) -> int:
    """Render one typed action result and return an informative exit status."""
    console = Console()
    if as_json:
        console.print(
            result.model_dump_json(indent=2), markup=False, highlight=False
        )
    else:
        console.print(result.message, markup=False)
        for error in result.errors:
            console.print(error, style="yellow", markup=False)
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

    if options.identifier == "recipe":
        from sec_nlp.app.workspace.recipes import load_recipe

        if options.settings is None:
            raise ValueError("research recipe requires --settings PATH")
        payload = TypeAdapter(JsonDict).validate_json(
            load_recipe(options.settings).model_dump_json()
        )
        result = asyncio.run(execute_research(store, "recipe", payload))
        Console().print(result.model_dump_json(indent=2), markup=False)
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
    Console().print(
        result.model_dump_json(indent=2), markup=False, highlight=False
    )
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
    store = WorkspaceStore(options.workspace)
    service = WorkspaceService(store)
    console = Console()
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
            status = _show_action(result, as_json=options.json_output)
            if not options.json_output:
                for filing in result.filings:
                    console.print(
                        f"{filing.accession_number}  {filing.form_type}  {filing.filed_date}  {filing.filing_url}",
                        markup=False,
                    )
            return status
        case "scan":
            if options.action == "save":
                spec = _scan(options)
                store.save_scan(spec)
                console.print(spec.model_dump_json(indent=2), markup=False)
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
            else:
                for spec in store.list_scans():
                    console.print(spec.model_dump_json(indent=2), markup=False)
        case "read":
            if options.bookmarked:
                store.set_bookmarked(options.identifier)
            if options.action == "manifest":
                manifest = asyncio.run(service.manifest(options.identifier))
                console.print(manifest.model_dump_json(indent=2), markup=False)
            else:
                content = asyncio.run(
                    service.read(options.identifier, filename=options.filename)
                )
                console.print(
                    content.model_dump_json(indent=2)
                    if options.json_output
                    else content.text,
                    markup=False,
                    highlight=False,
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
                console.print(entry.model_dump_json(indent=2), markup=False)
            else:
                for entry in store.list_notes(
                    accession_number=options.accession
                ):
                    if options.action == "review" and (
                        entry.review_on is None
                        or entry.review_on > datetime.now(UTC).date()
                    ):
                        continue
                    console.print(entry.model_dump_json(indent=2), markup=False)
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
                console.print(f"Workspace: {store.path}", markup=False)
            elif options.action == "open":
                from sec_nlp.tui.app import launch_workspace

                launch_workspace(store.path)
            elif options.action == "migrate":
                from sec_nlp.app.workspace.migrate import migrate_workspace

                if options.origin is None:
                    raise ValueError(
                        "Provide the original workspace with --from"
                    )
                console.print(
                    migrate_workspace(options.origin, store).model_dump_json(
                        indent=2
                    ),
                    markup=False,
                )
            elif options.action == "jobs":
                for job in store.list_jobs():
                    console.print(job.model_dump_json(indent=2), markup=False)
            elif options.action == "inbox":
                show_filings(
                    store,
                    unread=options.unread,
                    bookmarked=options.bookmarked,
                    limit=options.limit,
                )
            else:
                console.print(f"Workspace: {store.path}", markup=False)
                console.print(
                    store.load_settings().model_dump_json(indent=2),
                    markup=False,
                )
                for checkpoint in store.list_checkpoints():
                    console.print(
                        checkpoint.model_dump_json(indent=2), markup=False
                    )
        case "research":
            return _research(store, options, remaining)
        case "export":
            from sec_nlp.app.workspace.export import export_workspace

            if options.destination is None:
                raise ValueError("Choose an export destination")
            path = export_workspace(
                store, options.destination, output_format=options.export_format
            )
            console.print(f"Exported {path}", markup=False)
    return 0
