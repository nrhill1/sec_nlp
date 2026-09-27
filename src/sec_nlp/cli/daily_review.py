# src/sec_nlp/cli/daily_review.py
"""Expose cached Pulse activity, watchlist editing, and review actions.

The CLI presents the same typed results as the terminal. Listing and editing
local research state never fetch evidence or create provider jobs.
"""

import argparse
import json
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from sec_nlp.app.pulse.models import WatchItem, normalize_symbol
from sec_nlp.app.workspace.store import WorkspaceStore


@dataclass
class DailyReviewOptions(argparse.Namespace):
    """Hold optional arguments for the daily review command extensions.

    Attributes:
        operation: Nested list, acknowledgement, watchlist, or review operation.
        scope: Focused watchlist/topics or market-wide evidence.
        all_items: Include reviewed evidence in the activity listing.
        topic: Exact saved topic filter.
        publisher: Source name filter.
        form: Exact filing form filter.
        cursor: Opaque continuation cursor from a previous Pulse page.
        identities: Stable evidence identities to acknowledge.
        token: Acknowledgement token to undo.
        target_kind: Watchlist thesis or immutable journal target.
        target_id: Stable symbol or journal entry identifier.
        note: Authored completion or deferral note.
        next_review_on: Optional next review date.
        watch_name: Replacement watchlist display name when supplied.
        watch_aliases: Replacement aliases when supplied.
        watch_thesis: Replacement thesis when supplied.
        watch_invalidation: Replacement invalidation text when supplied.
        clear_review: Remove an existing watchlist review date.
    """

    operation: str = ""
    scope: Literal["focused", "all"] = "focused"
    all_items: bool = False
    topic: str = ""
    publisher: str = ""
    form: str = ""
    cursor: str | None = None
    identities: list[str] | None = None
    token: str = ""
    target_kind: Literal["watchlist", "journal"] = "journal"
    target_id: str = ""
    note: str = ""
    next_review_on: date | None = None
    watch_name: str | None = None
    watch_aliases: list[str] | None = None
    watch_thesis: str | None = None
    watch_invalidation: str | None = None
    clear_review: bool = False


def add_pulse_options(parser: argparse.ArgumentParser) -> None:
    """Add cached activity listing and explicit acknowledgement operations."""
    operations = parser.add_subparsers(dest="operation")
    listing = operations.add_parser(
        "list", help="List one cached activity page."
    )
    listing.add_argument(
        "--scope", choices=("focused", "all"), default="focused"
    )
    listing.add_argument("--all", dest="all_items", action="store_true")
    listing.add_argument("--symbol")
    listing.add_argument("--topic", default="")
    listing.add_argument("--source", dest="publisher", default="")
    listing.add_argument("--form", default="")
    listing.add_argument("--cursor")
    operations.add_parser(
        "overview", help="Show cached market and review status."
    )
    mark = operations.add_parser(
        "mark", help="Acknowledge explicit evidence identities."
    )
    mark.add_argument("identities", nargs="+")
    undo = operations.add_parser(
        "undo", help="Undo one acknowledgement operation."
    )
    undo.add_argument("token")


def add_watchlist_options(parser: argparse.ArgumentParser) -> None:
    """Add watchlist edits that preserve fields omitted from a command."""
    operations = parser.add_subparsers(dest="operation")
    operations.add_parser("list")
    saving = operations.add_parser(
        "save", help="Add or update one watched symbol."
    )
    saving.add_argument("symbol")
    saving.add_argument("--name", dest="watch_name")
    saving.add_argument("--aliases", dest="watch_aliases", nargs="*")
    saving.add_argument("--thesis", dest="watch_thesis")
    saving.add_argument("--invalidation", dest="watch_invalidation")
    schedule = saving.add_mutually_exclusive_group()
    schedule.add_argument("--review-on", type=date.fromisoformat)
    schedule.add_argument("--clear-review", action="store_true")
    removing = operations.add_parser("remove")
    removing.add_argument("symbol")


def add_review_options(parser: argparse.ArgumentParser) -> None:
    """Keep bare due-review listing and add completion and deferral actions."""
    operations = parser.add_subparsers(dest="operation")
    for operation in ("complete", "defer"):
        action = operations.add_parser(operation)
        action.add_argument("target_kind", choices=("watchlist", "journal"))
        action.add_argument("target_id")
        action.add_argument("--note", default="")
        action.add_argument(
            "--next-review-on",
            type=date.fromisoformat,
            required=operation == "defer",
        )


def _show_model(result: BaseModel) -> None:
    """Render an unwrapped typed result suitable for scripts and source inspection."""
    Console(soft_wrap=True).print(
        result.model_dump_json(indent=2), markup=False, highlight=False
    )


def show_pulse(
    store: WorkspaceStore,
    options: DailyReviewOptions,
    *,
    symbol: str | None,
    as_json: bool,
) -> None:
    """Run a cached Pulse action through the shared application service.

    Args:
        store: Open local workspace.
        options: Selected activity action and filters.
        symbol: Optional normalized watchlist filter.
        as_json: Render the typed page rather than a compact table.
    """
    from sec_nlp.app.workspace.pulse import (
        acknowledge,
        pulse_overview,
        pulse_page,
        undo_acknowledgement,
    )
    from sec_nlp.app.workspace.pulse_models import PulseFilters

    if options.operation == "overview":
        _show_model(pulse_overview(store))
    elif options.operation == "mark":
        token = acknowledge(store, tuple(options.identities or ()))
        Console(soft_wrap=True).print(
            json.dumps({"token": token}) if as_json else token,
            markup=False,
            highlight=False,
        )
    elif options.operation == "undo":
        undo_acknowledgement(store, options.token)
        Console().print(
            json.dumps({"undone": options.token})
            if as_json
            else "Acknowledgement undone.",
            markup=False,
        )
    else:
        page = pulse_page(
            store,
            filters=PulseFilters(
                scope=options.scope,
                new_only=not options.all_items,
                symbol=normalize_symbol(symbol) if symbol else "",
                topic=options.topic,
                source=options.publisher,
                form=options.form,
            ),
            cursor=options.cursor,
        )
        if as_json:
            _show_model(page)
            return
        table = Table(
            "State",
            "Discovered",
            "Source date",
            "Source",
            "Evidence",
            "Identity",
        )
        for item in page.items:
            table.add_row(
                "reviewed" if item.reviewed else "new",
                item.discovered_at.date().isoformat(),
                str(item.published_at or item.filing_date or "unknown"),
                item.source,
                item.title,
                item.identity,
            )
        Console(soft_wrap=True).print(table)
        if page.next_cursor:
            Console(soft_wrap=True).print(
                f"Next page: --cursor {page.next_cursor}", markup=False
            )


def edit_watchlist(
    store: WorkspaceStore,
    options: DailyReviewOptions,
    *,
    symbol: str | None,
    review_on: date | None,
) -> tuple[WatchItem, ...]:
    """Apply one watchlist edit while preserving unspecified authored fields.

    Args:
        store: Open local workspace.
        options: Selected operation and optional replacement fields.
        symbol: Ticker to save or remove.
        review_on: Explicit replacement review date.

    Returns:
        Current watchlist after any requested edit.

    Raises:
        ValueError: If an editing operation omits its symbol.
    """
    from sec_nlp.app.workspace.pulse import remove_watch_item, save_watch_item

    if options.operation in {"save", "remove"}:
        if not symbol:
            raise ValueError("Provide a watchlist symbol")
        ticker = normalize_symbol(symbol)
        if options.operation == "remove":
            remove_watch_item(store, ticker)
        else:
            existing = next(
                (
                    item
                    for item in store.load_settings().watchlist
                    if item.symbol == ticker
                ),
                WatchItem(symbol=ticker),
            )
            saved = WatchItem(
                symbol=ticker,
                name=options.watch_name
                if options.watch_name is not None
                else existing.name,
                aliases=tuple(options.watch_aliases)
                if options.watch_aliases is not None
                else existing.aliases,
                thesis=options.watch_thesis
                if options.watch_thesis is not None
                else existing.thesis,
                invalidation=options.watch_invalidation
                if options.watch_invalidation is not None
                else existing.invalidation,
                review_on=None
                if options.clear_review
                else review_on or existing.review_on,
            )
            save_watch_item(store, saved)
    return store.load_settings().watchlist


def run_review(store: WorkspaceStore, options: DailyReviewOptions) -> None:
    """List due reviews or append a completion/deferral without changing notes.

    Args:
        store: Open local workspace.
        options: Target, action, authored note, and replacement schedule.
    """
    from sec_nlp.app.workspace.pulse import record_review, review_due
    from sec_nlp.app.workspace.pulse_models import ReviewAction

    if options.operation in {"complete", "defer"}:
        action = ReviewAction(
            target_kind=options.target_kind,
            target_id=normalize_symbol(options.target_id)
            if options.target_kind == "watchlist"
            else options.target_id,
            action="complete" if options.operation == "complete" else "defer",
            note=options.note,
            next_review_on=options.next_review_on,
        )
        record_review(store, action)
        _show_model(action)
    else:
        records = review_due(store)
        Console(soft_wrap=True).print(
            "["
            + ",\n".join(item.model_dump_json(indent=2) for item in records)
            + "]",
            markup=False,
            highlight=False,
        )
