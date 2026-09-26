# src/sec_nlp/app/investing/rendering.py
"""Render reproducible investing evidence as a portable Markdown report.

Exports preserve source health, observation dates, and the distinction between
retrieved evidence and user-authored research. Provider text is escaped so it
cannot introduce markup or change the structure of the exported report.
"""

import re
import shlex
from datetime import UTC, date, datetime
from html import escape
from urllib.parse import quote

from pydantic import HttpUrl

from sec_nlp.app.investing.models import (
    Brief,
    MarketObservation,
)

_MARKET_NOTE = (
    "Provider closes are unadjusted, in each asset's listing currency; currency is "
    "unspecified by this feed. Returns use adjusted closes across one or five "
    "observed sessions, ending on the listed quote date. The current session "
    "may be incomplete: its provider close and returns that include it may "
    "be provisional, rather than final session values. Missing history stays "
    "missing. Different dates or session calendars are not aligned comparisons."
)
_NEWS_NOTE = (
    "Company and theme labels are phrase matches or explicit feed scope, "
    "not evidence of causation. Publication dates may be unknown. "
    "New means absent from the preceding compatible saved brief; on the "
    "first brief, every headline is new to this workspace."
)


def _markdown(value: str) -> str:
    """Escape prose so provider text cannot introduce Markdown or HTML."""
    plain = escape(value, quote=False).replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~=\-])", r"\\\1", plain)


def _markdown_link(label: str, url: HttpUrl) -> str:
    """Return an escaped label and an inert HTTP link destination."""
    destination = quote(str(url), safe="/:#?=&%+@;,$!-._~")
    return f"[{_markdown(label)}]({destination})"


def _timestamp(value: datetime | None) -> str:
    """Return an explicit UTC timestamp or a visible missing-date label."""
    if value is None:
        return "Publication date unknown"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _percentage(value: float | None) -> str:
    """Return a signed return percentage or a missing-history label."""
    return f"{value:+.2f}%" if value is not None else "Unavailable"


def _review_label(review_on: date | None, today: date) -> str:
    """Return the planned date and whether the review is due."""
    if review_on is None:
        return "Not scheduled"
    suffix = " · Review due" if review_on <= today else " · Planned"
    return review_on.isoformat() + suffix


def _due_count(brief: Brief) -> int:
    """Count due watchlist hypotheses and journal entries independently."""
    today = brief.generated_at.astimezone(UTC).date()
    reviews = tuple(
        item.review_on for item in brief.settings.watchlist
    ) + tuple(entry.review_on for entry in brief.journal)
    return sum(review is not None and review <= today for review in reviews)


def _market_symbols(brief: Brief) -> tuple[str, ...]:
    """Preserve requested assets even when quote retrieval failed entirely."""
    requested = tuple(item.symbol for item in brief.settings.watchlist)
    observed = tuple(item.symbol for item in brief.market)
    return tuple(
        dict.fromkeys(requested + brief.settings.benchmarks + observed)
    )


def _market_role(symbol: str, brief: Brief) -> str:
    """Describe watchlist and benchmark membership without implying a holding."""
    roles = []
    if any(item.symbol == symbol for item in brief.settings.watchlist):
        roles.append("Watchlist")
    if symbol in brief.settings.benchmarks:
        roles.append("Benchmark")
    return " · ".join(roles) or "Market evidence"


def _market_name(symbol: str, brief: Brief) -> str:
    """Return a configured company name for an observed asset."""
    return next(
        (
            item.name
            for item in brief.settings.watchlist
            if item.symbol == symbol
        ),
        "",
    )


def _quote_status(observation: MarketObservation | None) -> str:
    """Expose missing price or date fields before considering quote staleness."""
    if (
        observation is None
        or observation.close is None
        or observation.quote_date is None
    ):
        return "Missing"
    return "Stale" if observation.stale else "Observed"


def _commands(symbol: str) -> tuple[str, ...]:
    """Build copyable SEC drilldowns with each shell argument quoted."""
    return (
        shlex.join(("sec-nlp", "events", symbol)),
        shlex.join(
            ("sec-nlp", "retrieve", symbol, "--queries", "risk factors")
        ),
        shlex.join(("sec-nlp", "financials", symbol, "--periods", "4")),
    )


def _markdown_market(brief: Brief) -> list[str]:
    """Build complete market evidence rows including unavailable assets."""
    lines = [
        "## Market observations",
        "",
        _MARKET_NOTE,
        "",
        "| Asset | Role | Provider close · listing currency unspecified | Quote date | 1 observed session | 5 observed sessions | Sessions | Status |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    observations = {item.symbol: item for item in brief.market}
    for symbol in _market_symbols(brief):
        observation = observations.get(symbol)
        label = f"{symbol} {_market_name(symbol, brief)}".strip()
        asset = (
            _markdown_link(label, observation.source_url)
            if observation is not None
            else _markdown(label)
        )
        close = "Unavailable"
        quote_date = "Unknown"
        one_session = five_sessions = "Unavailable"
        sessions = 0
        if observation is not None:
            if observation.close is not None:
                close = f"{observation.close:,.2f}"
            if observation.quote_date is not None:
                quote_date = observation.quote_date.isoformat()
            one_session = _percentage(observation.change_1d_pct)
            five_sessions = _percentage(observation.change_5d_pct)
            sessions = observation.observations
        lines.append(
            f"| {asset} | {_market_role(symbol, brief)} | {close} | "
            f"{quote_date} | {one_session} | {five_sessions} | {sessions} | "
            f"{_quote_status(observation)} |"
        )
    if not _market_symbols(brief):
        lines.extend(("", "No market assets configured or observed."))
    return lines


def _markdown_research(brief: Brief) -> list[str]:
    """Build user-authored theses and journal entries separately from evidence."""
    today = brief.generated_at.astimezone(UTC).date()
    lines = [
        "## Your research · user-authored hypotheses",
        "",
        "These are your questions and interpretations, separate from retrieved evidence.",
        "",
    ]
    for item in brief.settings.watchlist:
        lines.extend(
            (
                f"### {_markdown(item.symbol)} · {_markdown(item.name or item.symbol)}",
                "",
                f"- Thesis: {_markdown(item.thesis or 'Not recorded')}",
                f"- Invalidation: {_markdown(item.invalidation or 'Not recorded')}",
                f"- Review: {_review_label(item.review_on, today)}",
                "",
            )
        )
    for theme in brief.settings.themes:
        lines.append(
            f"- Theme question · {_markdown(theme.name)}: "
            f"{_markdown(theme.question or 'No research question recorded')}"
        )
    if not brief.settings.watchlist and not brief.settings.themes:
        lines.append("No hypotheses or theme questions recorded.")
    lines.extend(("", "## Journal · your observations and interpretations", ""))
    for entry in brief.journal:
        lines.extend(
            (
                f"### {_markdown(entry.symbol or 'General observation')} · {_timestamp(entry.created_at)}",
                "",
                f"- Observation: {_markdown(entry.observation)}",
                f"- Thesis: {_markdown(entry.thesis or 'Not recorded')}",
                f"- Invalidation: {_markdown(entry.invalidation or 'Not recorded')}",
                f"- Review: {_review_label(entry.review_on, today)}",
                "- Evidence links: "
                + (
                    ", ".join(
                        _markdown_link(f"Source {position}", url)
                        for position, url in enumerate(entry.sources, start=1)
                    )
                    or "None recorded"
                ),
                "",
            )
        )
    if not brief.journal:
        lines.append("No journal entries yet.")
    return lines


def render_markdown(brief: Brief) -> str:
    """Render a portable report with escaped prose and source provenance.

    Args:
        brief: Frozen evidence snapshot and user research to display.

    Returns:
        A complete Markdown document that can be saved without extra assets.
    """
    successful = sum(source.status == "ok" for source in brief.sources)
    lines = [f"# {_markdown(brief.settings.name)}", ""]
    if brief.demo:
        lines.extend(
            (
                "> **SYNTHETIC DEMO — invented observations and headlines; not current market data.**",
                "",
            )
        )
    lines.extend(
        (
            f"Generated: {_timestamp(brief.generated_at)}",
            "",
            f"Goal: {_markdown(brief.settings.goal)}",
            "",
            f"- Source coverage: {successful}/{len(brief.sources)} successful sources",
            f"- New headlines: {sum(item.is_new for item in brief.headlines)}/{len(brief.headlines)}",
            f"- Reviews due: {_due_count(brief)} (watchlist theses and journal entries)",
            "",
            *_markdown_market(brief),
            "",
            "## Current events · sourced evidence",
            "",
            _NEWS_NOTE,
            "",
        )
    )
    for headline in brief.headlines:
        labels = ["NEW" if headline.is_new else "Previously seen"]
        labels.extend(headline.symbols)
        labels.extend(headline.themes)
        lines.extend(
            (
                f"### {_markdown_link(headline.title, headline.url)}",
                "",
                f"{_markdown(headline.source)} · {_timestamp(headline.published_at)}",
                "",
                "Tags: " + " · ".join(_markdown(label) for label in labels),
                "",
            )
        )
    if not brief.headlines:
        lines.extend(
            (
                "No headlines available in this brief. Check source coverage below.",
                "",
            )
        )
    lines.extend(("## Research checks", ""))
    lines.extend(f"- {_markdown(prompt)}" for prompt in brief.prompts)
    if not brief.prompts:
        lines.append("No research checks generated.")
    lines.extend(("", *_markdown_research(brief), "", "## Source coverage", ""))
    for source in brief.sources:
        lines.append(
            f"- **{_markdown(source.name)}** · {source.kind} · "
            f"{source.status.upper()} · {source.records} records: "
            f"{_markdown(source.detail or 'No additional detail')}"
        )
    if not brief.sources:
        lines.append("No source retrieval status recorded.")
    lines.extend(
        (
            "",
            "## SEC filing drilldowns",
            "",
            "Optional commands to investigate watched companies in the existing SEC workflows. "
            "Run separately with SEC contact configuration; filing coverage applies to SEC registrants.",
            "",
        )
    )
    for item in brief.settings.watchlist:
        lines.extend(
            (
                f"### {_markdown(item.symbol)}",
                "",
                "```shell",
                *_commands(item.symbol),
                "```",
                "",
            )
        )
    if not brief.settings.watchlist:
        lines.append("Add a watched company to get SEC drilldown commands.")
    lines.extend(("", f"Brief ID: {_markdown(brief.brief_id)}", ""))
    return "\n".join(lines)
