# tests/app/workspace/test_pulse.py
"""Test Pulse review persistence, projections, migration, and indexed queries.

Fixtures exercise ledger upgrades and evidence identity without remote sources or
native provider calls. Review acknowledgement stays separate from filing reads.
"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import HttpUrl, ValidationError

from sec_nlp.app.pulse.models import (
    Brief,
    Headline,
    JournalEntry,
    MarketObservation,
    PulseSettings,
    SourceStatus,
    Theme,
    WatchItem,
)
from sec_nlp.app.workspace import pulse_schema
from sec_nlp.app.workspace.models import ScanSpec
from sec_nlp.app.workspace.pulse import (
    acknowledge,
    export_pulse_state,
    pulse_item,
    pulse_overview,
    pulse_page,
    record_review,
    remove_watch_item,
    review_due,
    save_watch_item,
    undo_acknowledgement,
)
from sec_nlp.app.workspace.pulse_models import (
    PulseFilters,
    ReviewAction,
    SymbolMapping,
)
from sec_nlp.app.workspace.store import _SCHEMA, WorkspaceStore
from sec_nlp.core.edgar.filing_models import FilingEntity, FilingRecord

STAMP = datetime(2026, 9, 25, 14, tzinfo=UTC)


def profile() -> PulseSettings:
    """Build deterministic watchlist and topic settings."""
    return PulseSettings(
        watchlist=(
            WatchItem(symbol="ACME", name="Acme", review_on=date(2026, 9, 20)),
        ),
        themes=(Theme(name="Chips", keywords=("semiconductor",)),),
        benchmarks=(),
        company_feeds=False,
    )


def filing(index: int = 1) -> FilingRecord:
    """Build evidence whose accession prefix differs from the associated entity."""
    return FilingRecord(
        accession_number=f"0000000999-26-{index:06d}",
        entities=(
            FilingEntity(cik="123", name="Acme", role="reporting owner"),
        ),
        form_type="4/A",
        filed_date=date(2026, 9, 24),
        filing_url=HttpUrl(f"https://www.sec.gov/Archives/{index}-index.html"),
        submission_url=HttpUrl(f"https://www.sec.gov/Archives/{index}.txt"),
    )


def headline(index: int = 1) -> Headline:
    """Build a dated source item with a current-profile topic match."""
    return Headline(
        title=f"Acme semiconductor release {index}",
        url=HttpUrl(f"https://example.com/{index}"),
        source="Wire",
        published_at=STAMP,
    )


def workspace(tmp_path: Path) -> WorkspaceStore:
    """Create an offline workspace with explicit user settings."""
    store = WorkspaceStore(tmp_path)
    store.save_settings(profile())
    return store


def test_review_state_survives_refresh_restart_and_filing_read(
    tmp_path: Path,
) -> None:
    """Keep explicit acknowledgement independent of evidence retrieval and reading."""
    store = workspace(tmp_path)
    store.upsert_filings((filing(),), source="SEC", observed_at=STAMP)
    store.save_symbol_mappings(
        (SymbolMapping(symbol="ACME", cik="0000000123"),), STAMP
    )
    store.save_news((headline(),))
    page = pulse_page(store)
    assert len(page.items) == 2
    record = next(item for item in page.items if item.kind == "filing")
    assert "reporting owner" in record.reasons[0]
    assert record.discovered_at == STAMP
    assert record.filing_date == date(2026, 9, 24)
    store.set_read(filing().accession_number)
    assert len(pulse_page(store).items) == 2
    token = acknowledge(store, (record.identity,))
    store.upsert_filings((filing(),), source="index")
    store.save_news((headline(),))
    store = WorkspaceStore(tmp_path)
    assert len(pulse_page(store).items) == 1
    assert undo_acknowledgement(store, token) == 1
    assert len(pulse_page(store).items) == 2
    assert store.list_filings()[0].is_read


def test_cached_item_lookup_preserves_review_and_filing_read_state(
    tmp_path: Path,
) -> None:
    """Inspect evidence through its stable identity without review or source work."""
    store = workspace(tmp_path)
    store.upsert_filings((filing(),), source="SEC", observed_at=STAMP)
    store.save_symbol_mappings(
        (SymbolMapping(symbol="ACME", cik="0000000123"),), STAMP
    )
    expected = pulse_page(store).items[0]
    assert pulse_item(store, expected.identity) == expected
    assert not store.list_filings()[0].is_read
    assert store.list_jobs() == ()
    acknowledge(store, (expected.identity,))
    assert pulse_item(store, expected.identity).reviewed
    with pytest.raises(ValueError, match="not in this workspace"):
        pulse_item(store, "news:missing")


def test_keyset_pagination_marks_only_visible_and_keeps_new_arrivals(
    tmp_path: Path,
) -> None:
    """Avoid offset skips when refresh inserts newer evidence between pages."""
    store = workspace(tmp_path)
    store.upsert_filings(
        tuple(filing(index) for index in range(1, 112)), observed_at=STAMP
    )
    selected = PulseFilters(scope="all")
    page = pulse_page(store, selected)
    assert len(page.items) == 50 and page.next_cursor
    acknowledge(store, tuple(item.identity for item in page.items))
    store.upsert_filings((filing(200),), observed_at=STAMP + timedelta(days=1))
    second = pulse_page(store, selected, cursor=page.next_cursor)
    assert len(second.items) == 50
    assert not {item.identity for item in second.items} & {
        item.identity for item in page.items
    }
    assert (
        pulse_page(store, selected).items[0].accession_number
        == filing(200).accession_number
    )
    with pytest.raises(ValueError, match="cursor"):
        pulse_page(store, cursor="invalid")


def test_acknowledgement_is_atomic_and_undo_respects_later_decisions(
    tmp_path: Path,
) -> None:
    """Rollback mixed invalid selections and preserve subsequent review choices."""
    store = workspace(tmp_path)
    store.save_news((headline(),))
    identity = pulse_page(store).items[0].identity
    with pytest.raises(ValueError, match="not in this workspace"):
        acknowledge(store, (identity, "missing"))
    assert pulse_page(store).items
    original = acknowledge(store, (identity,))
    subsequent = acknowledge(store, (identity,))
    assert undo_acknowledgement(store, original) == 0
    assert not pulse_page(store).items
    assert undo_acknowledgement(store, subsequent) == 1
    assert not pulse_page(store).items
    with pytest.raises(ValueError, match="Unknown"):
        undo_acknowledgement(store, "missing")


def test_news_identity_bridge_preserves_both_acknowledgements_and_provenance(
    tmp_path: Path,
) -> None:
    """Merge aliases without losing independently reviewed canonical evidence."""
    store = workspace(tmp_path)
    first = headline()
    second = headline(2)
    store.save_news((first, second))
    page = pulse_page(store)
    identities = tuple(item.identity for item in page.items)
    tokens = {
        item.url: acknowledge(store, (item.identity,)) for item in page.items
    }
    bridge = first.model_copy(
        update={"title": second.title, "source": "Publisher"}
    )
    store.save_news((bridge,))
    merged = pulse_page(store, PulseFilters(new_only=False)).items
    assert len(merged) == 1 and merged[0].reviewed
    assert "Wire" in merged[0].source and "Publisher" in merged[0].source
    assert all(
        pulse_item(store, identity) == merged[0] for identity in identities
    )
    assert undo_acknowledgement(store, tokens[str(second.url)]) == 0
    assert not pulse_page(store).items
    store.save_news((bridge.model_copy(update={"published_at": None}),))
    assert store.list_news()[0].published_at == STAMP
    assert export_pulse_state(store).activity[0].reviewed


def test_recurring_and_undated_titles_survive(tmp_path: Path) -> None:
    """Date-qualified identity retains later releases and unrelated undated URLs."""
    store = workspace(tmp_path)
    first = headline()
    store.save_news(
        (
            first,
            first.model_copy(
                update={
                    "url": HttpUrl("https://example.com/later"),
                    "published_at": STAMP + timedelta(days=1),
                }
            ),
            first.model_copy(
                update={
                    "url": HttpUrl("https://example.com/undated"),
                    "published_at": None,
                }
            ),
            first.model_copy(
                update={
                    "url": HttpUrl("https://example.com/undated2"),
                    "published_at": None,
                }
            ),
        )
    )
    assert len(pulse_page(store).items) == 4


def test_profile_edit_recomputes_cached_matches_and_retains_removed_evidence(
    tmp_path: Path,
) -> None:
    """Update title and topic associations without retrieving or deleting evidence."""
    store = workspace(tmp_path)
    store.save_news((headline(),))
    assert pulse_page(store).items[0].symbols == ("ACME",)
    store.save_settings(
        PulseSettings(
            watchlist=(WatchItem(symbol="CHIP", aliases=("semiconductor",)),),
            company_feeds=False,
        )
    )
    assert pulse_page(store).items[0].symbols == ("CHIP",)
    assert not pulse_page(store, PulseFilters(symbol="ACME")).items
    remove_watch_item(store, "CHIP")
    assert not pulse_page(store).items
    assert len(pulse_page(store, PulseFilters(scope="all")).items) == 1


def test_mapped_entities_stale_registry_and_saved_scans_remain_explicit(
    tmp_path: Path,
) -> None:
    """Match declared entity roles and explicit scan evidence without CIK guesses."""
    store = workspace(tmp_path)
    store.upsert_filings((filing(),))
    assert not pulse_page(store).items
    store.save_symbol_mappings(
        (SymbolMapping(symbol="ACME", cik="0000000123"),), STAMP
    )
    store.save_symbol_mappings(
        (), STAMP + timedelta(days=1), error="Registry unavailable"
    )
    assert "stale registry" in pulse_page(store).items[0].reasons[0]
    remove_watch_item(store, "ACME")
    scan = ScanSpec(name="Owners", query="stock")
    store.save_scan(scan)
    store.save_scan_matches(scan.scan_id, (filing().accession_number,))
    assert pulse_page(store, PulseFilters(topic="Owners", form="4/A")).items[
        0
    ].topics == ("Owners",)
    assert not pulse_page(store, PulseFilters(form="4")).items


def test_overview_keeps_valid_quotes_across_empty_failed_demo_and_older_data(
    tmp_path: Path,
) -> None:
    """Separate latest attempt from latest dated successful quote evidence."""
    store = workspace(tmp_path)
    quote = MarketObservation(
        symbol="ACME",
        quote_date=date(2026, 9, 24),
        close=100,
        change_1d_pct=1,
        change_5d_pct=5,
        source_url=HttpUrl("https://finance.yahoo.com/quote/ACME"),
    )
    store.save_pulse_source(
        SourceStatus(name="ACME", kind="market", status="ok"),
        STAMP,
        market=(quote,),
    )
    store.save_pulse_source(
        SourceStatus(
            name="ACME", kind="market", status="error", detail="timeout"
        ),
        STAMP + timedelta(hours=1),
    )
    store.save_market_observations(
        (quote.model_copy(update={"close": 999}),),
        STAMP + timedelta(hours=2),
        demo=True,
    )
    store.save_market_observations(
        (
            quote.model_copy(
                update={"close": 1, "quote_date": date(2020, 1, 1)}
            ),
        ),
        STAMP + timedelta(hours=3),
    )
    overview = pulse_overview(store)
    assert overview.market[0].close == 100
    assert overview.market[0].change_5d_pct == 5
    assert overview.sources[0].status.status == "error"


def test_due_reviews_preserve_notes_and_explicit_watchlist_rescheduling(
    tmp_path: Path,
) -> None:
    """Apply complete and defer actions while keeping source journal immutable."""
    store = workspace(tmp_path)
    now = datetime.now(UTC)
    entry = JournalEntry(
        entry_id="a" * 32,
        created_at=STAMP,
        observation="Evidence",
        symbol="ACME",
        review_on=date(2026, 9, 20),
        sources=(HttpUrl("https://example.com/evidence"),),
    )
    store.save_note(entry)
    assert len(review_due(store, on=now.date())) == 2
    record_review(
        store,
        ReviewAction(
            target_kind="journal",
            target_id=entry.entry_id,
            action="defer",
            next_review_on=now.date() + timedelta(days=2),
        ),
    )
    record_review(
        store,
        ReviewAction(
            target_kind="watchlist",
            target_id="ACME",
            action="complete",
            note="Thesis checked",
        ),
    )
    assert not review_due(store, on=now.date())
    save_watch_item(store, WatchItem(symbol="ACME", review_on=now.date()))
    assert len(review_due(store, on=now.date())) == 1
    assert store.list_notes() == (entry,)
    assert len(export_pulse_state(store).reviews) == 2
    with pytest.raises(ValidationError, match="future"):
        ReviewAction(
            target_kind="journal",
            target_id=entry.entry_id,
            action="defer",
            next_review_on=now.date(),
        )
    with pytest.raises(ValidationError, match="note"):
        ReviewAction(
            target_kind="journal", target_id=entry.entry_id, action="complete"
        )


def legacy_workspace(tmp_path: Path) -> Path:
    """Create a genuine v1 ledger without any Pulse v2 tables."""
    (tmp_path / "config.json").write_text(
        profile().model_dump_json(), encoding="utf-8"
    )
    database = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(_SCHEMA)
        connection.execute("PRAGMA user_version=1")
    return database


def test_v1_migration_backfills_once_and_preserves_original_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backfill compatibility, quotes, and snapshot news without rewriting sources."""
    database = legacy_workspace(tmp_path)
    brief = Brief(
        brief_id="b" * 32,
        generated_at=STAMP,
        settings=profile(),
        headlines=(headline(),),
    )
    payload = brief.model_dump_json()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO briefs VALUES (?,?,?)",
            (brief.brief_id, STAMP.isoformat(), payload),
        )
    store = WorkspaceStore(tmp_path)
    assert store.latest_brief(profile()) == brief
    assert pulse_page(store).items[0].discovered_at == STAMP
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            connection.execute("SELECT payload FROM briefs").fetchone()[0]
            == payload
        )

    def reject_upgrade(*args: str) -> None:
        """Fail if an already-upgraded workspace replays historical data."""
        raise AssertionError("Migration repeated")

    monkeypatch.setattr(pulse_schema, "upgrade", reject_upgrade)
    assert WorkspaceStore(tmp_path).latest_brief(profile()) == brief


def test_failed_migration_rolls_back_schema_and_version(tmp_path: Path) -> None:
    """Keep a corrupt v1 snapshot unchanged and retryable after failure."""
    database = legacy_workspace(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO briefs VALUES ('broken','2026','{}')")
    with pytest.raises(ValidationError):
        WorkspaceStore(tmp_path)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='pulse_activity'"
        ).fetchall()
        assert (
            connection.execute("SELECT payload FROM briefs").fetchone()[0]
            == "{}"
        )


def test_future_version_is_not_modified(tmp_path: Path) -> None:
    """Reject newer workspace formats without rewriting profile or ledger schema."""
    database = legacy_workspace(tmp_path)
    before = (tmp_path / "config.json").read_bytes()
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=3")
    with pytest.raises(ValueError, match="version"):
        WorkspaceStore(tmp_path)
    assert (tmp_path / "config.json").read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


def test_indexes_support_bounded_inbox_activity_and_profile_lookup(
    tmp_path: Path,
) -> None:
    """Assert query plans use indexes instead of temporary sorts or table scans."""
    store = workspace(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        membership = str(
            connection.execute(
                "EXPLAIN QUERY PLAN SELECT 1 FROM artifact_membership WHERE accession=? AND current=0",
                ("missing",),
            ).fetchall()
        )
        activity = str(
            connection.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM pulse_activity WHERE reviewed=0 ORDER BY discovered_at DESC,identity DESC LIMIT 51"
            ).fetchall()
        )
        briefs = str(
            connection.execute(
                "EXPLAIN QUERY PLAN SELECT key FROM pulse_brief_index WHERE profile=? AND demo=0 ORDER BY timestamp DESC,key LIMIT 1",
                ("missing",),
            ).fetchall()
        )
    assert "membership_accession_current" in membership
    assert "pulse_activity_new" in activity and "TEMP B-TREE" not in activity
    assert "pulse_brief_profile" in briefs and "TEMP B-TREE" not in briefs


def test_manual_profile_edits_rebuild_only_relevance_on_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Detect offline JSON edits by fingerprint without replaying brief history."""
    store = workspace(tmp_path)
    store.save_news((headline(),))
    revised = PulseSettings(
        themes=(Theme(name="Industry", keywords=("semiconductor",)),),
        company_feeds=False,
    )
    (tmp_path / "config.json").write_text(
        revised.model_dump_json(), encoding="utf-8"
    )

    def reject_upgrade(*args: str) -> None:
        """Reject unnecessary history replay after a portable profile edit."""
        raise AssertionError("History replayed")

    monkeypatch.setattr(pulse_schema, "upgrade", reject_upgrade)
    reopened = WorkspaceStore(tmp_path)
    item = pulse_page(reopened).items[0]
    assert item.symbols == () and item.topics == ("Industry",)


def test_v1_saved_scan_results_backfill_focused_evidence(
    tmp_path: Path,
) -> None:
    """Retain explicit authored scan provenance from existing result files."""
    database = legacy_workspace(tmp_path)
    scan = ScanSpec(name="Legacy scan", query="ownership")
    evidence = filing()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO scans VALUES (?,?)",
            (scan.scan_id, scan.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO filings(accession,payload,form_type,filed_date,first_seen_at,last_seen_at,source) VALUES (?,?,?,?,?,?,?)",
            (
                evidence.accession_number,
                evidence.model_dump_json(),
                evidence.form_type,
                "2026-09-24",
                STAMP.isoformat(),
                STAMP.isoformat(),
                "efts",
            ),
        )
    output = tmp_path / "scans" / scan.scan_id
    output.mkdir(parents=True)
    saved = (
        '{"query":'
        + scan.model_dump_json()
        + ',"result":{"filings":['
        + evidence.model_dump_json()
        + '],"message":"Completed"}}'
    )
    (output / "legacy-job.json").write_text(saved, encoding="utf-8")
    store = WorkspaceStore(tmp_path)
    assert pulse_page(store).items[0].topics == ("Legacy scan",)
    assert (output / "legacy-job.json").read_text(encoding="utf-8") == saved


def test_interrupted_upgrade_leaves_v1_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback schema changes even when cancellation interrupts migration."""
    database = legacy_workspace(tmp_path)

    def interrupted(
        connection: sqlite3.Connection, settings: PulseSettings
    ) -> None:
        """Interrupt after the migration creates new tables."""
        raise KeyboardInterrupt

    monkeypatch.setattr(pulse_schema, "refresh_profile", interrupted)
    with pytest.raises(KeyboardInterrupt):
        WorkspaceStore(tmp_path)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='pulse_activity'"
        ).fetchall()


def test_novelty_uses_persistent_first_discovery_without_review_mutation(
    tmp_path: Path,
) -> None:
    """Retain report comparison semantics independently of the daily review queue."""
    store = workspace(tmp_path)
    older = headline()
    store.save_news((older,))
    refresh_started = datetime.now(UTC)
    fresh = headline(2)
    store.save_news((fresh,))
    novelty = store.news_novelty((older, fresh), refresh_started)
    assert [item.is_new for item in novelty] == [False, True]
    assert len(pulse_page(store).items) == 2


def test_migration_keeps_newer_news_payload_when_importing_older_briefs(
    tmp_path: Path,
) -> None:
    """Preserve original live news dates, titles, and discovery timestamps."""
    database = legacy_workspace(tmp_path)
    previous = headline()
    latest = previous.model_copy(
        update={
            "title": "Acme corrected semiconductor release",
            "published_at": STAMP + timedelta(days=1),
        }
    )
    brief = Brief(
        brief_id="c" * 32,
        generated_at=STAMP,
        settings=profile(),
        headlines=(previous,),
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO news VALUES (?,?,?,?)",
            (
                "retained",
                STAMP.isoformat(),
                latest.model_dump_json(),
                STAMP.isoformat(),
            ),
        )
        connection.execute(
            "INSERT INTO briefs VALUES (?,?,?)",
            (brief.brief_id, STAMP.isoformat(), brief.model_dump_json()),
        )
    store = WorkspaceStore(tmp_path)
    assert store.list_news() == (latest,)
    assert pulse_page(store).items[0].title == latest.title
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT first_seen_at FROM news").fetchone()[0]
            == STAMP.isoformat()
        )


def test_company_feed_collision_labels_keep_explicit_scope(
    tmp_path: Path,
) -> None:
    """Retain generated company-feed scope when a configured feed shares its name."""
    store = workspace(tmp_path)
    store.save_settings(profile().model_copy(update={"company_feeds": True}))
    store.save_news(
        (
            headline().model_copy(
                update={
                    "title": "Quarterly update",
                    "source": "Yahoo Finance: ACME (company)",
                }
            ),
        )
    )
    assert pulse_page(store).items[0].symbols == ("ACME",)


def test_overlapping_source_commits_share_one_news_identity(
    tmp_path: Path,
) -> None:
    """Serialize deduplication reads and writes across independent source workers."""
    store = workspace(tmp_path)
    evidence = headline()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(store.save_news, ((evidence,), (evidence,)))
        )
    assert sum(result[0].is_new for result in results) == 1
    assert len(pulse_page(store).items) == 1
