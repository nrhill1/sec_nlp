# src/sec_nlp/cli/daily_tables.py
"""Render cached daily research as ordinary terminal tables and evidence text.

These views preserve full identities and source links in scrollback. Source and
authored text remain literal, and presentation never fetches or acknowledges data.
"""

from collections.abc import Sequence
from datetime import datetime

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from sec_nlp.app.pulse.models import WatchItem
from sec_nlp.app.workspace.pulse_models import (
    DueReview,
    PulseItem,
    PulseOverview,
    PulsePage,
    ReviewAction,
)


def _table(title: str, *columns: str) -> Table:
    """Build an inline table with visible separation between multiline rows."""
    return Table(
        *columns,
        title=Text(title, style="bold cyan"),
        title_justify="left",
        box=box.SIMPLE,
        show_lines=True,
        header_style="bold",
        expand=True,
    )


def _stamp(value: datetime) -> str:
    """Retain the source timezone and minute-level timestamp in readable text."""
    return value.isoformat(sep=" ", timespec="minutes")


def _literal(console: Console, value: str) -> None:
    """Print authored or provider text without markup, highlighting, or truncation."""
    console.print(Text(value), soft_wrap=True)


def show_activity(page: PulsePage) -> None:
    """Render one activity page with dates, match reasons, and usable identities."""
    console = Console()
    console.print(Text("Evidence · cached Pulse activity", style="bold cyan"))
    if not page.items:
        _literal(console, "No activity matches these filters.")
        _literal(
            console,
            "Use workspace pulse list --scope all for market-wide evidence; "
            "add --all to include reviewed items.",
        )
        return
    table = _table("", "# / state", "Evidence / source", "Dates / relevance")
    for index, item in enumerate(page.items, 1):
        published = (
            _stamp(item.published_at)
            if item.published_at
            else str(item.filing_date or "unknown")
        )
        details = (
            f"Published/filed: {published}\n"
            f"Discovered: {_stamp(item.discovered_at)}\n"
            f"Match: {'; '.join(item.reasons) or 'No current profile match'}"
        )
        table.add_row(
            Text(f"{index} · {'reviewed' if item.reviewed else 'new'}"),
            Text(f"{item.title}\nSource: {item.source}"),
            Text(details),
        )
    console.print(table)
    _literal(console, "Evidence IDs and source links:")
    for index, item in enumerate(page.items, 1):
        _literal(console, f"{index}. {item.identity}\n   {item.url}")
    _literal(
        console,
        "Inspect: workspace pulse show ID · Review: workspace pulse mark ID",
    )
    if page.next_cursor:
        _literal(
            console,
            f"Next page: add --cursor {page.next_cursor} to the same list filters.",
        )


def show_evidence(item: PulseItem) -> None:
    """Display complete cached source provenance without opening or reviewing it."""
    console = Console()
    console.print(Text("Evidence", style="bold cyan"))
    _literal(console, item.title)
    table = _table("", "Field", "Value")
    values = (
        ("Kind", item.kind),
        ("Review state", "reviewed" if item.reviewed else "new"),
        ("Source", item.source),
        (
            "Published / accepted",
            _stamp(item.published_at) if item.published_at else "unknown",
        ),
        ("Filing date", str(item.filing_date or "unknown")),
        ("Discovered", _stamp(item.discovered_at)),
        ("Symbols", ", ".join(item.symbols) or "None"),
        ("Topics / scans", ", ".join(item.topics) or "None"),
    )
    for label, value in values:
        table.add_row(Text(label), Text(value))
    console.print(table)
    _literal(console, f"Identity: {item.identity}\nSource URL: {item.url}")
    console.print(Text("Relevance", style="bold cyan"))
    for reason in item.reasons or (
        "No current watchlist, topic, or saved scan match.",
    ):
        _literal(console, f"• {reason}")
    _literal(
        console,
        "Relevance labels are matching context, not an investment conclusion.",
    )
    if item.accession_number:
        _literal(console, f"Read filing: sec-nlp read {item.accession_number}")


def show_overview(overview: PulseOverview, *, as_json: bool) -> None:
    """Display usable quotes separately from the latest provider attempts.

    Args:
        overview: Cached market evidence, provider attempts, mappings, and reviews.
        as_json: Preserve the shared typed result for scripting.
    """
    console = Console()
    if as_json:
        _literal(console, overview.model_dump_json(indent=2))
        return
    console.print(
        Text(
            "Evidence · latest successful market observations",
            style="bold cyan",
        )
    )
    market = _table(
        "",
        "Symbol",
        "As of",
        "Close",
        "1 session %",
        "5 sessions %",
        "Freshness",
    )
    for quote in overview.market:
        market.add_row(
            Text(quote.symbol),
            Text(str(quote.quote_date or "unknown")),
            Text(f"{quote.close:,.2f}" if quote.close is not None else "—"),
            Text(
                f"{quote.change_1d_pct:+.2f}"
                if quote.change_1d_pct is not None
                else "—"
            ),
            Text(
                f"{quote.change_5d_pct:+.2f}"
                if quote.change_5d_pct is not None
                else "—"
            ),
            Text("stale" if quote.stale else "current"),
        )
    if overview.market:
        console.print(market)
        for quote in overview.market:
            _literal(console, f"{quote.symbol}: {quote.source_url}")
        _literal(
            console,
            "Close uses the listing currency; session changes use adjusted closes.",
        )
    else:
        _literal(console, "No successful cached market observations.")
    sources = _table(
        "Latest refresh outcomes",
        "Source / kind",
        "Completed",
        "Outcome",
        "Detail",
    )
    for source in overview.sources:
        sources.add_row(
            Text(f"{source.status.name}\n{source.status.kind}"),
            Text(_stamp(source.observed_at)),
            Text(f"{source.status.status}\n{source.status.records} records"),
            Text(source.status.detail or "—"),
        )
    if overview.sources:
        console.print(sources)
    else:
        _literal(console, "No cached source outcomes.")
    if overview.mappings:
        mappings = _table(
            "SEC symbol mappings", "Symbol / CIK", "Company", "Status / checked"
        )
        for mapping in overview.mappings:
            mappings.add_row(
                Text(f"{mapping.symbol}\n{mapping.cik}"),
                Text(mapping.name or "—"),
                Text(
                    f"{'stale' if mapping.stale else 'confirmed'}\n{_stamp(mapping.checked_at)}\n{mapping.detail}".rstrip()
                ),
            )
        console.print(mappings)
        for mapping in overview.mappings:
            _literal(
                console, f"{mapping.symbol} registry: {mapping.source_url}"
            )
    show_reviews(overview.due_reviews)


def show_watchlist(items: Sequence[WatchItem], *, as_json: bool) -> None:
    """Render authored watchlist settings or preserve the existing JSON array.

    Args:
        items: Current watchlist with aliases and original authored schedules.
        as_json: Render the portable records for scripting.
    """
    console = Console()
    if as_json:
        _literal(
            console,
            "["
            + ",\n".join(item.model_dump_json(indent=2) for item in items)
            + "]",
        )
        return
    if not items:
        _literal(
            console,
            "Watchlist is empty. Add an asset with workspace watchlist save SYMBOL.",
        )
        return
    table = _table(
        "Watchlist · authored research",
        "Asset / aliases",
        "Thesis / invalidation",
        "Original review date",
    )
    for item in items:
        table.add_row(
            Text(
                f"{item.symbol} · {item.name or 'Unnamed'}\nAliases: {', '.join(item.aliases) or 'None'}"
            ),
            Text(
                f"Thesis: {item.thesis or 'Not set'}\nInvalidation: {item.invalidation or 'Not set'}"
            ),
            Text(str(item.review_on or "Not scheduled")),
        )
    console.print(table)
    _literal(
        console,
        "Use journal review for due dates after completion or deferral.",
    )


def show_reviews(records: Sequence[DueReview]) -> None:
    """Render the effective due queue with target identities for explicit actions."""
    console = Console()
    console.print(
        Text(f"Research reviews · {len(records)} due", style="bold cyan")
    )
    if not records:
        _literal(console, "No research reviews are due.")
        return
    table = _table("", "Target / due", "Review / thesis", "Invalidation")
    for item in records:
        table.add_row(
            Text(
                f"{item.target_kind} · {item.symbol or 'Journal'}\n{item.review_on}"
            ),
            Text(f"{item.title}\nThesis: {item.thesis or 'Not set'}"),
            Text(item.invalidation or "Not set"),
        )
    console.print(table)
    for item in records:
        _literal(console, f"Target: {item.target_kind} {item.target_id}")
    _literal(
        console,
        "Use journal review complete KIND ID --note '...' or defer KIND ID --next-review-on YYYY-MM-DD.",
    )


def show_review_action(action: ReviewAction) -> None:
    """Render the saved decision with its new effective schedule and history ID."""
    console = Console()
    console.print(Text("Research review recorded", style="bold cyan"))
    _literal(console, f"Target: {action.target_kind} {action.target_id}")
    _literal(console, f"Action: {action.action}\nNote: {action.note or 'None'}")
    _literal(
        console, f"Next review: {action.next_review_on or 'Schedule completed'}"
    )
    _literal(
        console,
        f"Review ID: {action.review_id}\nRecorded: {_stamp(action.created_at)}",
    )
