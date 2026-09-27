# src/sec_nlp/app/workspace/pulse_schema.py
"""Maintain SQLite projections for bounded Pulse activity and overview queries.

Schema upgrades and backfills run inside the caller's explicit transaction. The
portable evidence payloads stay unchanged; projections can be rebuilt from them
and hold user acknowledgements separately from filing reading state.
"""

import hashlib
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.app.pulse.models import Brief, Headline, PulseSettings
from sec_nlp.app.workspace.models import ScanSpec
from sec_nlp.app.workspace.pulse_models import PulseItem, PulseSource
from sec_nlp.core.edgar.filing_models import FilingRecord
from sec_nlp.core.news.normalization import phrase_matches

SCHEMA = """
CREATE INDEX IF NOT EXISTS membership_accession_current ON artifact_membership(accession,current);
CREATE INDEX IF NOT EXISTS filing_order ON filings(filed_date DESC,accepted_at DESC,accession DESC);
CREATE TABLE IF NOT EXISTS pulse_activity (
 identity TEXT PRIMARY KEY, kind TEXT NOT NULL, reference TEXT NOT NULL,
 discovered_at TEXT NOT NULL, source TEXT NOT NULL, form_type TEXT NOT NULL DEFAULT '',
 payload TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0, review_token TEXT NOT NULL DEFAULT '',
 UNIQUE(kind,reference)
);
CREATE INDEX IF NOT EXISTS pulse_activity_order ON pulse_activity(discovered_at DESC,identity DESC);
CREATE INDEX IF NOT EXISTS pulse_activity_new ON pulse_activity(reviewed,discovered_at DESC,identity DESC);
CREATE INDEX IF NOT EXISTS pulse_activity_source ON pulse_activity(source,discovered_at DESC,identity DESC);
CREATE INDEX IF NOT EXISTS pulse_activity_form ON pulse_activity(form_type,discovered_at DESC,identity DESC);
CREATE TABLE IF NOT EXISTS pulse_matches (
 identity TEXT NOT NULL REFERENCES pulse_activity(identity) ON DELETE CASCADE,
 kind TEXT NOT NULL, value TEXT NOT NULL, reason TEXT NOT NULL,
 PRIMARY KEY(identity,kind,value,reason)
);
CREATE INDEX IF NOT EXISTS pulse_match_filter ON pulse_matches(kind,value,identity);
CREATE TABLE IF NOT EXISTS pulse_symbols (symbol TEXT PRIMARY KEY,cik TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS pulse_symbol_cik ON pulse_symbols(cik);
CREATE TABLE IF NOT EXISTS pulse_watchlist (symbol TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS pulse_watch_schedule (symbol TEXT PRIMARY KEY,review_on TEXT,changed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_market (symbol TEXT PRIMARY KEY,timestamp TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_sources (kind TEXT NOT NULL,name TEXT NOT NULL,timestamp TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(kind,name));
CREATE TABLE IF NOT EXISTS pulse_brief_index (key TEXT PRIMARY KEY REFERENCES briefs(key),profile TEXT NOT NULL,demo INTEGER NOT NULL,timestamp TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS pulse_brief_profile ON pulse_brief_index(profile,demo,timestamp DESC,key);
CREATE INDEX IF NOT EXISTS pulse_brief_latest ON pulse_brief_index(demo,timestamp DESC,key);
CREATE TABLE IF NOT EXISTS pulse_reviews (key TEXT PRIMARY KEY,kind TEXT NOT NULL,target TEXT NOT NULL,timestamp TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS pulse_review_target ON pulse_reviews(kind,target,timestamp DESC,key DESC);
CREATE TABLE IF NOT EXISTS pulse_identity_redirect (identity TEXT PRIMARY KEY,canonical TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_ack_operations (token TEXT PRIMARY KEY,undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS pulse_acknowledgements (token TEXT NOT NULL,identity TEXT NOT NULL,previous INTEGER NOT NULL,previous_token TEXT NOT NULL,PRIMARY KEY(token,identity));
CREATE TABLE IF NOT EXISTS pulse_scan_matches (scan_id TEXT NOT NULL,accession TEXT NOT NULL,PRIMARY KEY(scan_id,accession));
CREATE INDEX IF NOT EXISTS pulse_scan_accession ON pulse_scan_matches(accession,scan_id);
"""


class _ScanResult(BaseModel):
    """Read the filing portion of an authored scan result for migration."""

    model_config = ConfigDict(frozen=True, extra="ignore")
    filings: tuple[FilingRecord, ...] = Field(
        description="Retained scan evidence."
    )


class _ScanSnapshot(BaseModel):
    """Read preserved query provenance without interpreting file instructions."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    query: ScanSpec = Field(description="Original saved query settings.")
    result: _ScanResult = Field(description="Original selected evidence.")


def text_field(row: sqlite3.Row, key: str) -> str:
    """Read text while failing visibly on a corrupt ledger value.

    Args:
        row: SQLite result with named columns.
        key: Required text column.

    Raises:
        ValueError: If the column contains a non-text value.
    """
    value = row[key]
    if not isinstance(value, str):
        raise ValueError(f"Invalid Pulse ledger text field: {key}")
    return value


def profile_fingerprint(settings: PulseSettings) -> str:
    """Return the stable digest for exact frozen profile compatibility."""
    return hashlib.sha256(settings.model_dump_json().encode()).hexdigest()


def project_news(
    connection: sqlite3.Connection,
    key: str,
    headline: Headline,
    discovered_at: str,
    settings: PulseSettings,
) -> None:
    """Upsert one activity row and recompute current headline relevance.

    Args:
        connection: Transaction owned by the caller.
        key: Canonical durable news identity.
        headline: Normalized source evidence.
        discovered_at: Preserved first discovery timestamp in UTC ISO format.
        settings: Current profile defining feed, symbol, and topic matches.
    """
    identity = f"news:{key}"
    item = PulseItem(
        identity=identity,
        kind="news",
        title=headline.title,
        source=headline.source,
        url=str(headline.url),
        discovered_at=datetime.fromisoformat(discovered_at),
        published_at=headline.published_at,
    )
    connection.execute(
        "INSERT INTO pulse_activity(identity,kind,reference,discovered_at,source,payload) VALUES (?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET source=excluded.source,payload=excluded.payload",
        (
            identity,
            "news",
            key,
            discovered_at,
            headline.source,
            item.model_dump_json(),
        ),
    )
    connection.execute(
        "DELETE FROM pulse_matches WHERE identity=?", (identity,)
    )
    scopes = {
        symbol
        for feed in settings.feeds
        if feed.name in headline.source.split(" | ")
        for symbol in feed.symbols
    }
    for watched in settings.watchlist:
        scoped = watched.symbol in scopes or (
            settings.company_feeds
            and any(
                re.fullmatch(
                    re.escape(f"Yahoo Finance: {watched.symbol}")
                    + r"(?: \(company\))*",
                    source,
                )
                for source in headline.source.split(" | ")
            )
        )
        matched = next(
            (
                phrase
                for phrase in (watched.name, *watched.aliases)
                if phrase_matches(headline.title, phrase)
            ),
            "",
        )
        ticker = phrase_matches(headline.title, watched.symbol, ticker=True)
        if scoped or matched or ticker:
            reason = f"{watched.symbol}: " + (
                "company feed scope"
                if scoped
                else f"headline phrase {matched}"
                if matched
                else "headline ticker"
            )
            connection.execute(
                "INSERT INTO pulse_matches VALUES (?,?,?,?)",
                (identity, "symbol", watched.symbol, reason),
            )
    for theme in settings.themes:
        matched = next(
            (
                keyword
                for keyword in theme.keywords
                if phrase_matches(headline.title, keyword)
            ),
            "",
        )
        if matched:
            connection.execute(
                "INSERT INTO pulse_matches VALUES (?,?,?,?)",
                (
                    identity,
                    "topic",
                    theme.name,
                    f"{theme.name}: headline phrase {matched}",
                ),
            )


def project_filing(
    connection: sqlite3.Connection,
    filing: FilingRecord,
    source: str,
    discovered_at: str,
) -> None:
    """Project SEC evidence without guessing issuer identity from accessions.

    Args:
        connection: Transaction owned by the caller.
        filing: Canonical filing with provider-declared entity associations.
        source: Discovery provider label.
        discovered_at: Preserved first discovery timestamp in UTC ISO format.
    """
    item = PulseItem(
        identity=f"filing:{filing.accession_number}",
        kind="filing",
        title=f"{filing.form_type} · "
        + (
            ", ".join(
                dict.fromkeys(
                    entity.name or entity.cik for entity in filing.entities
                )
            )
            or filing.accession_number
        ),
        source=source,
        url=str(filing.filing_url),
        discovered_at=datetime.fromisoformat(discovered_at),
        published_at=filing.accepted_at,
        filing_date=filing.filed_date,
        accession_number=filing.accession_number,
    )
    connection.execute(
        "INSERT INTO pulse_activity(identity,kind,reference,discovered_at,source,form_type,payload) VALUES (?,?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET source=excluded.source,form_type=excluded.form_type,payload=excluded.payload",
        (
            item.identity,
            "filing",
            filing.accession_number,
            discovered_at,
            source,
            filing.form_type,
            item.model_dump_json(),
        ),
    )


def project_brief(connection: sqlite3.Connection, brief: Brief) -> None:
    """Index snapshot compatibility and update non-demo market/source projections.

    Args:
        connection: Transaction owned by the caller.
        brief: Immutable historical report; synthetic reports only enter the index.
    """
    stamp = brief.generated_at.astimezone(UTC).isoformat()
    connection.execute(
        "INSERT OR REPLACE INTO pulse_brief_index VALUES (?,?,?,?)",
        (
            brief.brief_id,
            profile_fingerprint(brief.settings),
            int(brief.demo),
            stamp,
        ),
    )
    if brief.demo:
        return
    for observation in brief.market:
        if observation.close is not None and observation.quote_date is not None:
            connection.execute(
                "INSERT INTO pulse_market VALUES (?,?,?) ON CONFLICT(symbol) DO UPDATE SET timestamp=excluded.timestamp,payload=excluded.payload WHERE json_extract(excluded.payload,'$.quote_date')>=json_extract(pulse_market.payload,'$.quote_date') AND excluded.timestamp>=pulse_market.timestamp",
                (observation.symbol, stamp, observation.model_dump_json()),
            )
    for status in brief.sources:
        result = PulseSource(status=status, observed_at=brief.generated_at)
        connection.execute(
            "INSERT INTO pulse_sources VALUES (?,?,?,?) ON CONFLICT(kind,name) DO UPDATE SET timestamp=excluded.timestamp,payload=excluded.payload WHERE excluded.timestamp>=pulse_sources.timestamp",
            (status.kind, status.name, stamp, result.model_dump_json()),
        )


def refresh_profile(
    connection: sqlite3.Connection, settings: PulseSettings
) -> None:
    """Recompute cached relevance after an explicit offline profile edit.

    Args:
        connection: Transaction owned by the caller.
        settings: Current validated profile and review dates.
    """
    for item in settings.watchlist:
        review_date = item.review_on.isoformat() if item.review_on else None
        connection.execute(
            "INSERT INTO pulse_watch_schedule VALUES (?,?,?) ON CONFLICT(symbol) DO UPDATE SET review_on=excluded.review_on,changed_at=excluded.changed_at WHERE pulse_watch_schedule.review_on IS NOT excluded.review_on",
            (item.symbol, review_date, datetime.now(UTC).isoformat()),
        )
    connection.execute("DELETE FROM pulse_watchlist")
    connection.executemany(
        "INSERT INTO pulse_watchlist VALUES (?)",
        ((item.symbol,) for item in settings.watchlist),
    )
    for row in connection.execute(
        "SELECT key,payload,first_seen_at FROM news"
    ).fetchall():
        project_news(
            connection,
            text_field(row, "key"),
            Headline.model_validate_json(text_field(row, "payload")),
            text_field(row, "first_seen_at"),
            settings,
        )
    connection.execute(
        "INSERT OR REPLACE INTO metadata VALUES ('pulse_profile',?)",
        (profile_fingerprint(settings),),
    )


def upgrade(
    connection: sqlite3.Connection,
    settings: PulseSettings,
    workspace: Path,
    save_news: Callable[[tuple[Headline, ...], datetime], tuple[Headline, ...]],
) -> None:
    """Create v2 structures and backfill once within an existing transaction.

    Args:
        connection: Explicit migration transaction owned by the caller.
        settings: Validated current profile used for cached relevance.
        workspace: Workspace root containing authored scan result files.
        save_news: Ledger writer that preserves existing canonical news payloads.

    Raises:
        ValueError: If retained evidence cannot be validated. The caller rolls
            back every schema and projection change along with the version.
    """
    for statement in SCHEMA.split(";"):
        if statement.strip():
            connection.execute(statement)
    for row in connection.execute(
        "SELECT payload,source,first_seen_at FROM filings"
    ).fetchall():
        project_filing(
            connection,
            FilingRecord.model_validate_json(text_field(row, "payload")),
            text_field(row, "source"),
            text_field(row, "first_seen_at"),
        )
    refresh_profile(connection, settings)
    for row in connection.execute(
        "SELECT payload FROM briefs ORDER BY timestamp,key"
    ).fetchall():
        brief = Brief.model_validate_json(text_field(row, "payload"))
        project_brief(connection, brief)
        if not brief.demo:
            save_news(brief.headlines, brief.generated_at)
    for path in sorted((workspace / "scans").glob("*/*.json")):
        snapshot = _ScanSnapshot.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        connection.executemany(
            "INSERT OR IGNORE INTO pulse_scan_matches VALUES (?,?)",
            (
                (snapshot.query.scan_id, filing.accession_number)
                for filing in snapshot.result.filings
            ),
        )
    connection.execute("PRAGMA user_version=2")
