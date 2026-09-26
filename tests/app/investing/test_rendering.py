# tests/app/investing/test_rendering.py
"""Tests for investing report content, provenance, and safe local rendering."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from html.parser import HTMLParser

import pytest
from pydantic import HttpUrl

from sec_nlp.app.investing.models import (
    Brief,
    Headline,
    InvestingSettings,
    JournalEntry,
    MarketObservation,
    SourceStatus,
    Theme,
    WatchItem,
)
from sec_nlp.app.investing.rendering import render_markdown


class _DocumentParser(HTMLParser):
    """Collect rendered tags and prose to detect injected HTML structure.

    Attributes:
        elements: Opening tags and their parsed attributes.
        prose: Text content from the rendered document.
    """

    def __init__(self) -> None:
        """Construct a parser retaining tags and decoded document text."""
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.prose: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Record opening tags and attributes for structural assertions."""
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        """Record text after HTML character references have been decoded."""
        self.prose.append(data)


@pytest.fixture
def brief() -> Brief:
    """Build a fixed snapshot covering missing data, review dates, and sources."""
    return Brief(
        brief_id="a" * 32,
        generated_at=datetime(2026, 9, 26, 12, 0, tzinfo=UTC),
        settings=InvestingSettings(
            name="Research desk",
            goal="Understand chip demand and revisit my own thesis.",
            watchlist=(
                WatchItem(
                    symbol="ACME",
                    name="Acme Semiconductors",
                    thesis="Customers will expand capacity.",
                    invalidation="Orders decline across two reports.",
                    review_on=date(2026, 9, 26),
                ),
                WatchItem(symbol="MISSING"),
            ),
            benchmarks=("SPY",),
            themes=(
                Theme(
                    name="Manufacturing",
                    keywords=("capacity",),
                    question="Are capacity plans changing?",
                ),
            ),
        ),
        market=(
            MarketObservation(
                symbol="ACME",
                close=120.5,
                quote_date=date(2026, 9, 25),
                change_1d_pct=3.25,
                change_5d_pct=-2.5,
                observations=7,
                source_url=HttpUrl("https://example.com/acme"),
            ),
            MarketObservation(
                symbol="SPY",
                close=590,
                quote_date=date(2026, 9, 18),
                observations=1,
                stale=True,
                source_url=HttpUrl("https://example.com/spy"),
            ),
        ),
        headlines=(
            Headline(
                title="Acme expands production capacity",
                source="Company release",
                url=HttpUrl("https://example.com/article"),
                symbols=("ACME",),
                themes=("Manufacturing",),
                published_at=datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
            ),
            Headline(
                title="An undated item",
                source="Industry feed",
                url=HttpUrl("https://example.com/undated"),
                is_new=False,
            ),
        ),
        sources=(
            SourceStatus(
                name="Company release", kind="news", status="ok", records=1
            ),
            SourceStatus(name="ACME", kind="market", status="ok", records=7),
            SourceStatus(
                name="Failed feed",
                kind="news",
                status="error",
                detail="Feed returned HTTP 503.",
            ),
            SourceStatus(
                name="Empty feed",
                kind="news",
                status="empty",
                detail="No records in the requested window.",
            ),
        ),
        journal=(
            JournalEntry(
                entry_id="b" * 32,
                created_at=datetime(2026, 9, 25, 11, 0, tzinfo=UTC),
                observation="The release mentions capacity plans.",
                thesis="I expect more orders.",
                invalidation="Revisit if utilization falls.",
                review_on=date(2026, 10, 1),
                sources=(HttpUrl("https://example.com/research"),),
            ),
        ),
        prompts=("What evidence explains the observed move?",),
    )


@pytest.mark.parametrize("renderer", (render_markdown,))
def test_report_preserves_evidence_research_and_source_gaps(
    brief: Brief, renderer: Callable[[Brief], str]
) -> None:
    """Keep dated evidence, user hypotheses, and source failures visible."""
    report = renderer(brief)
    parser = _DocumentParser()
    parser.feed(report)
    visible = " ".join(parser.prose).replace("\\", "")

    for expected in (
        "Research desk",
        "Understand chip demand",
        "Acme expands production capacity",
        "2026-09-25 10:00 UTC",
        "Publication date unknown",
        "Previously seen",
        "Manufacturing",
        "Customers will expand capacity.",
        "Orders decline across two reports.",
        "2026-09-26 · Review due",
        "The release mentions capacity plans.",
        "2026-10-01 · Planned",
        "What evidence explains the observed move?",
        "Feed returned HTTP 503.",
        "No records in the requested window.",
    ):
        assert expected in visible
    assert "https://example.com/article" in report
    assert "https://example.com/research" in report


@pytest.mark.parametrize("renderer", (render_markdown,))
def test_market_output_exposes_unaligned_dates_and_missing_history(
    brief: Brief, renderer: Callable[[Brief], str]
) -> None:
    """Show requested missing assets without inventing prices or comparisons."""
    report = renderer(brief)

    for expected in (
        "ACME",
        "MISSING",
        "Benchmark",
        "Watchlist",
        "120.50",
        "+3.25%",
        "-2.50%",
        "2026-09-25",
        "2026-09-18",
        "Stale",
        "Missing",
        "Unavailable",
        "listing currency",
        "unspecified",
        "adjusted closes",
        "observed sessions",
        "Provider close",
        "current session may be incomplete",
        "returns that include it may be provisional",
        "not aligned comparisons",
    ):
        assert expected in report
    assert "$" not in report
    assert "percentage points" not in report


def test_untrusted_text_cannot_add_tags_attributes_or_scripts() -> None:
    """Render malicious prose literally across every configurable text area."""
    payload = '<script>injected()</script><img src=x onerror="injected()">'
    malicious = Brief(
        brief_id="c" * 32,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        settings=InvestingSettings(
            name=payload,
            goal=payload,
            watchlist=(
                WatchItem(
                    symbol="ACME",
                    name=payload,
                    thesis=payload,
                    invalidation=payload,
                ),
            ),
            themes=(
                Theme(name=payload, keywords=(payload,), question=payload),
            ),
        ),
        headlines=(
            Headline(
                title=payload,
                source=payload,
                url=HttpUrl('https://example.com/a_(b)?query="onclick=bad'),
                symbols=(payload,),
                themes=(payload,),
            ),
        ),
        market=(
            MarketObservation(
                symbol=payload, source_url=HttpUrl("https://example.com/quote")
            ),
        ),
        sources=(
            SourceStatus(
                name=payload, kind="news", status="error", detail=payload
            ),
        ),
        journal=(
            JournalEntry(
                entry_id="d" * 32,
                created_at=datetime(2026, 9, 26, tzinfo=UTC),
                observation=payload,
                thesis=payload,
                invalidation=payload,
            ),
        ),
        prompts=(payload,),
    )
    markdown = render_markdown(malicious)
    assert "<script>" not in markdown
    assert "<img" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "a_%28b%29" in markdown


def test_markdown_escapes_formatting_and_line_injection() -> None:
    """Keep user-authored Markdown and embedded HTML inert in exported prose."""
    brief = Brief(
        brief_id="e" * 32,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        settings=InvestingSettings(
            name="**Fake heading**",
            goal="[click](javascript:bad)\n# heading | `code` <b>bold</b>",
            benchmarks=(),
        ),
    )
    report = render_markdown(brief)

    assert r"\*\*Fake heading\*\*" in report
    assert r"\[click\]\(javascript:bad\)" in report
    assert "\n# heading" not in report
    assert r"\| \`code\` &lt;b&gt;bold&lt;/b&gt;" in report


@pytest.mark.parametrize("renderer", (render_markdown,))
def test_demo_and_empty_states_are_unambiguous(
    renderer: Callable[[Brief], str],
) -> None:
    """Label synthetic data prominently and explain empty report sections."""
    brief = Brief(
        brief_id="f" * 32,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        settings=InvestingSettings(benchmarks=()),
        demo=True,
    )
    report = renderer(brief)

    assert "SYNTHETIC DEMO" in report
    assert "not current market data" in report
    assert "No market assets configured or observed." in report
    assert "No headlines available" in report
    assert "No source retrieval status recorded." in report
    assert "No journal entries yet." in report


def test_review_count_includes_only_due_watchlist_and_journal_entries() -> None:
    """Count same-day and overdue reviews while excluding future plans."""
    brief = Brief(
        brief_id="1" * 32,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        settings=InvestingSettings(
            watchlist=(
                WatchItem(symbol="ACME", review_on=date(2026, 9, 26)),
                WatchItem(symbol="FUTURE", review_on=date(2026, 9, 27)),
            ),
        ),
        journal=(
            JournalEntry(
                entry_id="2" * 32,
                created_at=datetime(2026, 9, 20, tzinfo=UTC),
                observation="Revisit this observation.",
                review_on=date(2026, 9, 25),
            ),
        ),
    )

    assert "Reviews due: 2" in render_markdown(brief)


@pytest.mark.parametrize("renderer", (render_markdown,))
def test_sec_drilldowns_quote_symbols_with_shell_metacharacters(
    renderer: Callable[[Brief], str],
) -> None:
    """Quote caret symbols so copied commands cannot trigger shell expansion."""
    brief = Brief(
        brief_id="3" * 32,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        settings=InvestingSettings(watchlist=(WatchItem(symbol="^GSPC"),)),
    )
    parser = _DocumentParser()
    parser.feed(renderer(brief))
    visible = " ".join(parser.prose)

    assert "sec-nlp events '^GSPC'" in visible
    assert "sec-nlp retrieve '^GSPC' --queries 'risk factors'" in visible
    assert "sec-nlp financials '^GSPC' --periods 4" in visible
