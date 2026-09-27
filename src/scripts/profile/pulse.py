# src/scripts/profile/pulse.py
"""Measure offline Pulse queries against a representative cached workspace.

The fixture contains 50,000 filings, 10,000 headlines, and 1,000 snapshots in a
temporary directory. Timings are local observations, not CI thresholds; no
provider is contacted and no existing user workspace is changed.
"""

import sqlite3
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from pydantic import HttpUrl
from rich.console import Console

from sec_nlp.app.pulse.models import (
    Brief,
    Headline,
    PulseSettings,
    Theme,
    WatchItem,
)
from sec_nlp.app.pulse.service import _deduplicate
from sec_nlp.app.workspace.pulse import pulse_page
from sec_nlp.app.workspace.pulse_models import PulseFilters, SymbolMapping
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.filing_models import FilingEntity, FilingRecord


def seed_workspace(path: Path) -> WorkspaceStore:
    """Build deterministic cached evidence for query and first-paint measurements.

    Args:
        path: Empty directory owned by the benchmark caller.

    Returns:
        A local workspace populated with the stated acceptance fixture sizes.
    """
    store = WorkspaceStore(path)
    now = datetime(2026, 9, 27, 12, tzinfo=UTC)
    settings = PulseSettings(
        watchlist=(WatchItem(symbol="DEMO", name="Example Issuer"),),
        themes=(Theme(name="Capacity", keywords=("capacity",)),),
        benchmarks=(),
        company_feeds=False,
    )
    store.save_settings(settings)
    store.save_symbol_mappings(
        (SymbolMapping(symbol="DEMO", cik="0000000123", checked_at=now),),
        checked_at=now,
    )
    for batch in range(50):
        records = tuple(
            FilingRecord(
                accession_number=f"0000000123-26-{index:06}",
                entities=(
                    FilingEntity(
                        cik="123", name="Example Issuer", role="issuer"
                    ),
                ),
                form_type="8-K",
                filed_date=date(2026, 9, 25),
                accepted_at=now - timedelta(seconds=index),
                filing_url=HttpUrl(
                    f"https://www.sec.gov/Archives/{index}-index.html"
                ),
                submission_url=HttpUrl(
                    f"https://www.sec.gov/Archives/{index}.txt"
                ),
            )
            for index in range(batch * 1000, (batch + 1) * 1000)
        )
        store.upsert_filings(records, source="sec-index", observed_at=now)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "INSERT INTO artifact_membership SELECT 'benchmark-index',accession,1 FROM filings"
        )
    headlines = tuple(
        Headline(
            title=f"Capacity report {index}",
            source="Fixture publisher",
            url=HttpUrl(f"https://example.com/news/{index}"),
            published_at=now - timedelta(minutes=index),
        )
        for index in range(10_000)
    )
    store.save_news(headlines)
    for index in range(1000):
        store.save_brief(
            Brief(
                brief_id=f"{index:032x}",
                settings=settings,
                generated_at=now - timedelta(hours=index),
                headlines=headlines[:60],
            )
        )
    return store


def _measure(operation: Callable[[], int]) -> float:
    """Return the median milliseconds from five completed local operations."""
    samples: list[float] = []
    for _ in range(5):
        started = perf_counter()
        operation()
        samples.append((perf_counter() - started) * 1000)
    return round(median(samples), 2)


def measure_workspace(store: WorkspaceStore) -> dict[str, float]:
    """Measure bounded cache reads and deduplication without network access.

    Args:
        store: Workspace populated by the offline fixture generator.

    Returns:
        Median milliseconds for inbox, focused/all activity, and overlapping news.
    """
    headlines = list(store.list_news(limit=5000))
    overlapping = [*headlines, *headlines]
    return {
        "inbox_500_ms": _measure(lambda: len(store.list_filings(limit=500))),
        "pulse_focused_50_ms": _measure(lambda: len(pulse_page(store).items)),
        "pulse_all_50_ms": _measure(
            lambda: len(
                pulse_page(store, filters=PulseFilters(scope="all")).items
            )
        ),
        "pulse_missing_symbol_ms": _measure(
            lambda: len(
                pulse_page(store, filters=PulseFilters(symbol="UNKNOWN")).items
            )
        ),
        "deduplicate_10000_ms": _measure(
            lambda: len(_deduplicate(overlapping, None))
        ),
    }


def main() -> None:
    """Create a temporary offline fixture and report local acceptance timings."""
    with TemporaryDirectory(prefix="sec-nlp-pulse-") as temporary:
        store = seed_workspace(Path(temporary))
        Console().print_json(data=measure_workspace(store))


if __name__ == "__main__":
    main()
