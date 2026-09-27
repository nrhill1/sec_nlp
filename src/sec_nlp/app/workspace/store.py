# src/sec_nlp/app/workspace/store.py
"""Persist research evidence and user review state in a local SQLite ledger.

Each operation uses its own short-lived connection so terminal workers share a
workspace safely. Filing batches and their coverage checkpoints commit together.
Large document snapshots are atomic files addressed by URL hash; configuration
remains editable JSON and never starts background work.
"""

import hashlib
import os
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

from platformdirs import user_data_path
from pydantic import BaseModel

from sec_nlp.app.pulse.models import (
    Brief,
    Headline,
    JournalEntry,
    PulseSettings,
)
from sec_nlp.app.pulse.storage import starter_settings
from sec_nlp.app.workspace.models import (
    CachePointer,
    InboxItem,
    JobRecord,
    ScanSpec,
    SourceCheckpoint,
)
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingDocument,
    FilingManifest,
    FilingRecord,
)
from sec_nlp.core.news.normalization import dated_title_key, url_key

type SqlValue = str | int | None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS filings (
 accession TEXT PRIMARY KEY, payload TEXT NOT NULL, form_type TEXT NOT NULL,
 filed_date TEXT, accepted_at TEXT, is_read INTEGER NOT NULL DEFAULT 0,
 bookmarked INTEGER NOT NULL DEFAULT 0, first_seen_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
 accession TEXT NOT NULL REFERENCES filings(accession) ON DELETE CASCADE,
 cik TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL,
 PRIMARY KEY(accession,cik,role)
);
CREATE INDEX IF NOT EXISTS entity_cik ON entities(cik);
CREATE INDEX IF NOT EXISTS filing_date ON filings(filed_date DESC);
CREATE TABLE IF NOT EXISTS artifact_membership (
 artifact_url TEXT NOT NULL, accession TEXT NOT NULL REFERENCES filings(accession),
 current INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(artifact_url,accession)
);
CREATE TABLE IF NOT EXISTS scans (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checkpoints (
 source TEXT NOT NULL, scope TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(source,scope)
);
CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, timestamp TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manifests (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cache_pointers (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS news (key TEXT PRIMARY KEY, timestamp TEXT NOT NULL, payload TEXT NOT NULL, first_seen_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS news_aliases (
 identity TEXT PRIMARY KEY, news_key TEXT NOT NULL REFERENCES news(key)
);
CREATE TABLE IF NOT EXISTS notes (key TEXT PRIMARY KEY, timestamp TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS note_filings (
 note_id TEXT NOT NULL REFERENCES notes(key) ON DELETE CASCADE,
 accession TEXT NOT NULL, PRIMARY KEY(note_id,accession)
);
CREATE TABLE IF NOT EXISTS briefs (key TEXT PRIMARY KEY, timestamp TEXT NOT NULL, payload TEXT NOT NULL);
"""


def _atomic_write(path: Path, content: str) -> None:
    """Replace one file only after its complete UTF-8 contents reach disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _text(row: sqlite3.Row, key: str) -> str:
    """Read a required text field and expose corrupt ledger rows explicitly."""
    value = row[key]
    if not isinstance(value, str):
        raise ValueError(f"Invalid workspace ledger text field: {key}")
    return value


def _timestamp(value: datetime) -> str:
    """Normalize an aware timestamp for stable ledger sorting."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Workspace timestamps must include a timezone")
    return value.astimezone(UTC).isoformat()


def _row_limit(value: int | None) -> int:
    """Translate an explicit unbounded export into SQLite's unlimited sentinel."""
    if value is None:
        return -1
    if value < 1:
        raise ValueError("limit must be positive or None")
    return value


def _news_identities(headline: Headline) -> tuple[str, ...]:
    """Build shared URL and optional UTC-date/title aliases for one headline."""
    identities = (f"url:{url_key(headline.url)}",)
    dated = dated_title_key(headline.title, headline.published_at)
    return (*identities, f"title:{dated}") if dated else identities


class WorkspaceStore:
    """Own durable filing, observation, and user-authored workspace records.

    Connections are scoped to methods rather than shared between threads. The
    store never contacts a provider or marks filings read during discovery.

    Attributes:
        path: Resolved workspace directory.
        database_path: SQLite ledger file inside the workspace.
    """

    def __init__(self, workspace: Path | None = None) -> None:
        """Open a local workspace, creating an offline starter profile if absent."""
        self.path = (
            (
                workspace
                if workspace is not None
                else user_data_path("sec-nlp", appauthor=False) / "workspace"
            )
            .expanduser()
            .resolve()
        )
        self.path.mkdir(parents=True, exist_ok=True)
        self.database_path = self.path / "ledger.sqlite3"
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError(
                    f"Unsupported workspace ledger version: {version}"
                )
            connection.executescript(_SCHEMA)
            connection.execute("PRAGMA user_version = 1")
            config = self.path / "config.json"
            if not config.exists():
                _atomic_write(
                    config, starter_settings().model_dump_json(indent=2) + "\n"
                )
                connection.execute(
                    "INSERT OR IGNORE INTO metadata VALUES ('profile_origin','default')"
                )
            else:
                connection.execute(
                    "INSERT OR IGNORE INTO metadata VALUES ('profile_origin','user')"
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield an isolated transaction and always close its connection."""
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _read_models[T: BaseModel](
        self, model: type[T], sql: str, parameters: tuple[SqlValue, ...] = ()
    ) -> tuple[T, ...]:
        """Validate JSON records returned by a parameterized ledger query."""
        with self._connect() as connection:
            return tuple(
                model.model_validate_json(_text(row, "payload"))
                for row in connection.execute(sql, parameters)
            )

    def load_settings(self) -> PulseSettings:
        """Return the editable profile without initiating refresh jobs."""
        return PulseSettings.model_validate_json(
            (self.path / "config.json").read_text(encoding="utf-8")
        )

    def save_settings(self, settings: PulseSettings) -> None:
        """Atomically save an explicitly edited profile without fetching sources."""
        _atomic_write(
            self.path / "config.json", settings.model_dump_json(indent=2) + "\n"
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO metadata VALUES ('profile_origin','user')"
            )

    def import_settings(self, settings: PulseSettings) -> bool:
        """Initialize untouched starter settings once from a migrated profile."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='profile_origin'"
            ).fetchone()
            if (
                row is None
                or _text(row, "value") != "default"
                or self.load_settings() != starter_settings()
            ):
                return False
            _atomic_write(
                self.path / "config.json",
                settings.model_dump_json(indent=2) + "\n",
            )
            connection.execute(
                "UPDATE metadata SET value='imported' WHERE key='profile_origin'"
            )
            return True

    def _upsert_filings(
        self,
        connection: sqlite3.Connection,
        filings: Sequence[FilingRecord],
        source: str,
        observed_at: datetime,
    ) -> int:
        """Merge accession evidence while preserving user state and entity roles."""
        stamp = _timestamp(observed_at)
        inserted = 0
        for filing in filings:
            row = connection.execute(
                "SELECT payload FROM filings WHERE accession=?",
                (filing.accession_number,),
            ).fetchone()
            if row is not None:
                previous = FilingRecord.model_validate_json(
                    _text(row, "payload")
                )
                entities = {
                    (entity.cik, entity.role): entity
                    for entity in previous.entities
                }
                for entity in filing.entities:
                    key = (entity.cik, entity.role)
                    if entity.name or key not in entities:
                        entities[key] = entity
                filing = filing.model_copy(
                    update={
                        "entities": tuple(entities.values()),
                        "filed_date": filing.filed_date or previous.filed_date,
                        "accepted_at": filing.accepted_at
                        or previous.accepted_at,
                    }
                )
            else:
                inserted += 1
            connection.execute(
                "INSERT INTO filings(accession,payload,form_type,filed_date,accepted_at,first_seen_at,last_seen_at,source) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(accession) DO UPDATE SET payload=excluded.payload,form_type=excluded.form_type,filed_date=excluded.filed_date,accepted_at=excluded.accepted_at,last_seen_at=excluded.last_seen_at,source=excluded.source",
                (
                    filing.accession_number,
                    filing.model_dump_json(),
                    filing.form_type,
                    filing.filed_date.isoformat()
                    if filing.filed_date
                    else None,
                    _timestamp(filing.accepted_at)
                    if filing.accepted_at
                    else None,
                    stamp,
                    stamp,
                    source,
                ),
            )
            connection.executemany(
                "INSERT INTO entities VALUES (?,?,?,?) ON CONFLICT(accession,cik,role) DO UPDATE SET name=excluded.name",
                (
                    (
                        filing.accession_number,
                        entity.cik,
                        entity.name,
                        entity.role,
                    )
                    for entity in filing.entities
                ),
            )
        return inserted

    def upsert_filings(
        self,
        filings: Sequence[FilingRecord],
        *,
        source: str = "",
        observed_at: datetime | None = None,
    ) -> int:
        """Merge discovered accessions and return the number first seen locally.

        Args:
            filings: Validated accession evidence, possibly from overlapping pages.
            source: Most recent discovery provider.
            observed_at: Optional aware retrieval time for reproducible imports.
        """
        with self._connect() as connection:
            return self._upsert_filings(
                connection, filings, source, observed_at or datetime.now(UTC)
            )

    def ingest_filings(
        self, filings: Sequence[FilingRecord], checkpoint: SourceCheckpoint
    ) -> int:
        """Commit an index's filings and its successful checkpoint atomically.

        Args:
            filings: Fully parsed index contents.
            checkpoint: Coverage record produced after parsing succeeds.

        Returns:
            Number of previously unseen accessions.
        """
        with self._connect() as connection:
            inserted = self._upsert_filings(
                connection, filings, checkpoint.source, checkpoint.checked_at
            )
            self._record_membership(
                connection, filings, checkpoint, reconcile=False
            )
            self._save_checkpoint(connection, checkpoint)
            return inserted

    def _record_membership(
        self,
        connection: sqlite3.Connection,
        filings: Sequence[FilingRecord],
        checkpoint: SourceCheckpoint,
        *,
        reconcile: bool,
    ) -> None:
        """Record index provenance and optionally identify withdrawn memberships."""
        if not checkpoint.artifact_url:
            return
        watermark = (
            date.fromisoformat(checkpoint.cursor)
            if reconcile and checkpoint.cursor is not None
            else None
        )
        if reconcile:
            covered_date = watermark.isoformat() if watermark else None
            connection.execute(
                "UPDATE artifact_membership SET current=0 WHERE artifact_url=? AND (? IS NULL OR accession IN (SELECT accession FROM filings WHERE filed_date IS NULL OR filed_date<=?))",
                (checkpoint.artifact_url, covered_date, covered_date),
            )
        connection.executemany(
            "INSERT INTO artifact_membership VALUES (?,?,1) ON CONFLICT(artifact_url,accession) DO UPDATE SET current=1",
            (
                (checkpoint.artifact_url, filing.accession_number)
                for filing in filings
            ),
        )
        if reconcile:
            address = urlsplit(checkpoint.artifact_url)
            quarter = re.fullmatch(
                r"/Archives/edgar/full-index/(\d{4})/(QTR[1-4])/[^/]+",
                address.path,
            )
            if address.hostname in {"www.sec.gov", "sec.gov"} and quarter:
                for host in ("www.sec.gov", "sec.gov"):
                    daily_prefix = f"https://{host}/Archives/edgar/daily-index/{quarter.group(1)}/{quarter.group(2)}/"
                    daily_cutoff = (
                        f"{daily_prefix}master.{watermark:%Y%m%d}.idx"
                        if watermark is not None
                        else None
                    )
                    connection.execute(
                        "UPDATE artifact_membership AS daily SET current=EXISTS(SELECT 1 FROM artifact_membership AS quarterly WHERE quarterly.artifact_url=? AND quarterly.accession=daily.accession AND quarterly.current=1) WHERE daily.artifact_url LIKE ? AND (? IS NULL OR daily.artifact_url<=?)",
                        (
                            checkpoint.artifact_url,
                            daily_prefix + "%",
                            daily_cutoff,
                            daily_cutoff,
                        ),
                    )

    def reconcile_index(
        self, filings: Sequence[FilingRecord], checkpoint: SourceCheckpoint
    ) -> int:
        """Replace complete index membership while retaining disappeared filing evidence.

        Args:
            filings: Complete contents of a successfully parsed full index.
            checkpoint: Successful artifact coverage with its exact URL.

        Returns:
            Number of newly discovered accessions. Removed memberships become
            provenance warnings, while bookmarks, notes, and content remain.
            Daily evidence after the full snapshot's watermark is preserved.

        Raises:
            ValueError: If complete artifact coverage was not supplied.
        """
        if checkpoint.status != "complete" or not checkpoint.artifact_url:
            raise ValueError(
                "Reconciliation requires a complete artifact checkpoint"
            )
        with self._connect() as connection:
            inserted = self._upsert_filings(
                connection, filings, checkpoint.source, checkpoint.checked_at
            )
            self._record_membership(
                connection, filings, checkpoint, reconcile=True
            )
            self._save_checkpoint(connection, checkpoint)
            return inserted

    def get_filing(self, accession: str) -> FilingRecord | None:
        """Return canonical evidence for an accession, if discovered locally."""
        records = self._read_models(
            FilingRecord,
            "SELECT payload FROM filings WHERE accession=?",
            (accession,),
        )
        return records[0] if records else None

    def get_filings(
        self, accessions: Sequence[str]
    ) -> tuple[FilingRecord, ...]:
        """Return existing filings in input order using one bounded-query connection.

        Missing accessions are skipped and repeated requested accessions are
        retained. Batches respect SQLite builds with small variable limits.
        """
        found: dict[str, FilingRecord] = {}
        unique = tuple(dict.fromkeys(accessions))
        with self._connect() as connection:
            for start in range(0, len(unique), 900):
                batch = unique[start : start + 900]
                placeholders = ",".join("?" for _ in batch)
                for row in connection.execute(
                    f"SELECT payload FROM filings WHERE accession IN ({placeholders})",
                    batch,
                ):
                    filing = FilingRecord.model_validate_json(
                        _text(row, "payload")
                    )
                    found[filing.accession_number] = filing
        return tuple(found[key] for key in accessions if key in found)

    def list_filings(
        self,
        *,
        unread_only: bool = False,
        bookmarked_only: bool = False,
        cik: str | None = None,
        forms: Sequence[str] = (),
        query: str = "",
        limit: int | None = 100,
    ) -> tuple[InboxItem, ...]:
        """Return filtered accession rows with persistent review state.

        Args:
            unread_only: Restrict results to unread filings.
            bookmarked_only: Restrict results to saved filings.
            cik: Match any associated entity CIK.
            forms: Match exact SEC form types.
            query: Literal case-insensitive text across metadata.
            limit: Maximum rows returned, or None for an unbounded export.

        Returns:
            Newest filings first, with missing dates retained visibly.
        """
        row_limit = _row_limit(limit)
        clauses: list[str] = []
        parameters: list[SqlValue] = []
        if unread_only:
            clauses.append("is_read=0")
        if bookmarked_only:
            clauses.append("bookmarked=1")
        if cik:
            clauses.append(
                "EXISTS(SELECT 1 FROM entities e WHERE e.accession=filings.accession AND e.cik=?)"
            )
            parameters.append(cik.zfill(10))
        if forms:
            clauses.append(
                "form_type IN (" + ",".join("?" for _ in forms) + ")"
            )
            parameters.extend(forms)
        if query.strip():
            clauses.append("payload LIKE ? ESCAPE '\\'")
            literal = (
                query.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            parameters.append(f"%{literal}%")
        condition = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(row_limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT *,EXISTS(SELECT 1 FROM artifact_membership a WHERE a.accession=filings.accession AND a.current=0) AS source_withdrawn FROM filings"
                + condition
                + " ORDER BY filed_date DESC,accepted_at DESC,accession DESC LIMIT ?",
                tuple(parameters),
            )
            return tuple(
                InboxItem(
                    filing=FilingRecord.model_validate_json(
                        _text(row, "payload")
                    ),
                    is_read=bool(row["is_read"]),
                    bookmarked=bool(row["bookmarked"]),
                    first_seen_at=datetime.fromisoformat(
                        _text(row, "first_seen_at")
                    ),
                    last_seen_at=datetime.fromisoformat(
                        _text(row, "last_seen_at")
                    ),
                    source=_text(row, "source"),
                    source_withdrawn=bool(row["source_withdrawn"]),
                )
                for row in rows
            )

    def _set_state(self, accession: str, column: str, value: bool) -> None:
        """Update one internally selected user-state column for a known filing."""
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE filings SET {column}=? WHERE accession=?",
                (int(value), accession),
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"Filing is not in this workspace: {accession}"
                )

    def set_read(self, accession: str, value: bool = True) -> None:
        """Record an explicit read or unread choice for a discovered filing."""
        self._set_state(accession, "is_read", value)

    def set_bookmarked(self, accession: str, value: bool = True) -> None:
        """Record an explicit saved or unsaved choice for a discovered filing."""
        self._set_state(accession, "bookmarked", value)

    def save_scan(self, scan: ScanSpec) -> None:
        """Save a scan definition without executing or scheduling it."""
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO scans VALUES (?,?)",
                (scan.scan_id, scan.model_dump_json()),
            )

    def list_scans(self) -> tuple[ScanSpec, ...]:
        """Return saved scan definitions in stable identifier order."""
        return self._read_models(
            ScanSpec, "SELECT payload FROM scans ORDER BY key"
        )

    def delete_scan(self, scan_id: str) -> None:
        """Delete a saved definition while preserving its existing run artifacts."""
        with self._connect() as connection:
            connection.execute("DELETE FROM scans WHERE key=?", (scan_id,))

    def _save_checkpoint(
        self, connection: sqlite3.Connection, checkpoint: SourceCheckpoint
    ) -> None:
        """Preserve successful coverage metadata when a later attempt fails."""
        if (
            checkpoint.status == "complete"
            and checkpoint.last_success_at is None
        ):
            checkpoint = checkpoint.model_copy(
                update={"last_success_at": checkpoint.checked_at}
            )
        row = connection.execute(
            "SELECT payload FROM checkpoints WHERE source=? AND scope=?",
            (checkpoint.source, checkpoint.scope),
        ).fetchone()
        if row is not None:
            previous = SourceCheckpoint.model_validate_json(
                _text(row, "payload")
            )
            checkpoint = checkpoint.model_copy(
                update={
                    "last_success_at": checkpoint.last_success_at
                    or previous.last_success_at,
                    "processed_at": checkpoint.processed_at
                    or previous.processed_at,
                    "content_hash": checkpoint.content_hash
                    or previous.content_hash,
                    "artifact_url": checkpoint.artifact_url
                    or previous.artifact_url,
                }
            )
        connection.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?)",
            (checkpoint.source, checkpoint.scope, checkpoint.model_dump_json()),
        )

    def save_checkpoint(self, checkpoint: SourceCheckpoint) -> None:
        """Record source coverage without changing filing review state."""
        with self._connect() as connection:
            self._save_checkpoint(connection, checkpoint)

    def list_checkpoints(self) -> tuple[SourceCheckpoint, ...]:
        """Return all coverage scopes, including partial and failed attempts."""
        return self._read_models(
            SourceCheckpoint,
            "SELECT payload FROM checkpoints ORDER BY source,scope",
        )

    def save_job(self, job: JobRecord) -> None:
        """Persist one operation's latest visible outcome."""
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?,?,?)",
                (job.job_id, _timestamp(job.updated_at), job.model_dump_json()),
            )

    def list_jobs(self, *, limit: int | None = 100) -> tuple[JobRecord, ...]:
        """Return recent operation outcomes, newest updates first."""
        return self._read_models(
            JobRecord,
            "SELECT payload FROM jobs ORDER BY timestamp DESC,key LIMIT ?",
            (_row_limit(limit),),
        )

    def save_manifest(self, manifest: FilingManifest) -> None:
        """Cache document choices without marking their parent accession read."""
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO manifests VALUES (?,?)",
                (manifest.filing.accession_number, manifest.model_dump_json()),
            )

    def get_manifest(self, accession: str) -> FilingManifest | None:
        """Return cached document choices for offline inspection."""
        records = self._read_models(
            FilingManifest,
            "SELECT payload FROM manifests WHERE key=?",
            (accession,),
        )
        return records[0] if records else None

    def save_cache_pointer(self, pointer: CachePointer) -> bool:
        """Register an immutable cache location and report whether it was new."""
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO cache_pointers VALUES (?,?)",
                (pointer.key, pointer.model_dump_json()),
            )
            return cursor.rowcount == 1

    def list_cache_pointers(self) -> tuple[CachePointer, ...]:
        """Return owned and external content locations without opening them."""
        return self._read_models(
            CachePointer, "SELECT payload FROM cache_pointers ORDER BY key"
        )

    def cache_document(self, content: DocumentContent) -> Path:
        """Atomically cache complete document text and original HTML for offline use."""
        key = str(content.document.url)
        path = (
            self.path
            / "documents"
            / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
        )
        _atomic_write(path, content.model_dump_json() + "\n")
        self.save_cache_pointer(
            CachePointer(key=key, path=path, media_type="application/json")
        )
        return path

    def load_document(self, document: FilingDocument) -> DocumentContent | None:
        """Return a cached full document, preserving missing-cache visibility."""
        pointers = self._read_models(
            CachePointer,
            "SELECT payload FROM cache_pointers WHERE key=?",
            (str(document.url),),
        )
        if not pointers or not pointers[0].path.is_file():
            return None
        content = DocumentContent.model_validate_json(
            pointers[0].path.read_text(encoding="utf-8")
        )
        if content.document.url != document.url:
            raise ValueError(
                "Cached document URL does not match requested evidence"
            )
        return content

    def save_news(self, headlines: Sequence[Headline]) -> tuple[Headline, ...]:
        """Merge URL and dated-title identities and return durable newness.

        Keep identity aliases when publishers edit titles or timestamps.
        Undated items have URL identity only, preserving recurring releases.
        """
        normalized: list[Headline] = []
        with self._connect() as connection:
            indexed = connection.execute(
                "SELECT value FROM metadata WHERE key='news_identity_version'"
            ).fetchone()
            if indexed is None:
                for row in connection.execute(
                    "SELECT key,payload FROM news ORDER BY first_seen_at,key"
                ):
                    previous = Headline.model_validate_json(
                        _text(row, "payload")
                    )
                    for identity in _news_identities(previous):
                        connection.execute(
                            "INSERT OR IGNORE INTO news_aliases VALUES (?,?)",
                            (identity, _text(row, "key")),
                        )
                connection.execute(
                    "INSERT INTO metadata VALUES ('news_identity_version','1')"
                )
            for headline in headlines:
                stamp = (
                    _timestamp(headline.published_at)
                    if headline.published_at
                    else ""
                )
                identities = _news_identities(headline)
                row = None
                for identity in identities:
                    row = connection.execute(
                        "SELECT news.key,first_seen_at FROM news JOIN news_aliases ON news.key=news_aliases.news_key WHERE identity=?",
                        (identity,),
                    ).fetchone()
                    if row is not None:
                        break
                key = (
                    _text(row, "key")
                    if row is not None
                    else hashlib.sha256(identities[0].encode()).hexdigest()
                )
                first_seen = (
                    _text(row, "first_seen_at")
                    if row is not None
                    else _timestamp(datetime.now(UTC))
                )
                headline = headline.model_copy(update={"is_new": row is None})
                connection.execute(
                    "INSERT INTO news VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET timestamp=excluded.timestamp,payload=excluded.payload",
                    (key, stamp, headline.model_dump_json(), first_seen),
                )
                for identity in identities:
                    connection.execute(
                        "INSERT OR IGNORE INTO news_aliases VALUES (?,?)",
                        (identity, key),
                    )
                normalized.append(headline)
        return tuple(normalized)

    def list_news(self, *, limit: int | None = 100) -> tuple[Headline, ...]:
        """Return saved sourced headlines, retaining undated items after dated ones."""
        return self._read_models(
            Headline,
            "SELECT payload FROM news ORDER BY timestamp DESC,key LIMIT ?",
            (_row_limit(limit),),
        )

    def _save_immutable(
        self,
        connection: sqlite3.Connection,
        table: str,
        key: str,
        timestamp: str,
        payload: str,
    ) -> bool:
        """Insert a new snapshot and reject conflicting reuse of its identity."""
        row = connection.execute(
            f"SELECT payload FROM {table} WHERE key=?", (key,)
        ).fetchone()
        if row is not None:
            if _text(row, "payload") != payload:
                raise ValueError(
                    f"Conflicting {table} record with existing identifier: {key}"
                )
            return False
        connection.execute(
            f"INSERT INTO {table} VALUES (?,?,?)", (key, timestamp, payload)
        )
        return True

    def save_note(
        self, entry: JournalEntry, *, related_accession: str | None = None
    ) -> bool:
        """Append immutable research text and optionally link it to an accession.

        Args:
            entry: User-authored journal entry with stable identity.
            related_accession: Optional filing reference independent of ticker.

        Returns:
            Whether a new entry was saved; identical reimports return false.
        """
        with self._connect() as connection:
            inserted = self._save_immutable(
                connection,
                "notes",
                entry.entry_id,
                _timestamp(entry.created_at),
                entry.model_dump_json(),
            )
            if related_accession:
                connection.execute(
                    "INSERT OR IGNORE INTO note_filings VALUES (?,?)",
                    (entry.entry_id, related_accession),
                )
            return inserted

    def list_notes(
        self, *, accession_number: str | None = None
    ) -> tuple[JournalEntry, ...]:
        """Return chronological research notes, optionally linked to one accession."""
        if accession_number:
            return self._read_models(
                JournalEntry,
                "SELECT payload FROM notes JOIN note_filings ON notes.key=note_filings.note_id WHERE accession=? ORDER BY timestamp,key",
                (accession_number,),
            )
        return self._read_models(
            JournalEntry, "SELECT payload FROM notes ORDER BY timestamp,key"
        )

    def save_brief(self, brief: Brief) -> bool:
        """Append an immutable observation snapshot and report whether it was new."""
        with self._connect() as connection:
            return self._save_immutable(
                connection,
                "briefs",
                brief.brief_id,
                _timestamp(brief.generated_at),
                brief.model_dump_json(),
            )

    def list_note_links(self) -> dict[str, tuple[str, ...]]:
        """Return every note-to-accession association for portable exports."""
        links: dict[str, tuple[str, ...]] = {}
        with self._connect() as connection:
            for row in connection.execute(
                "SELECT note_id,accession FROM note_filings ORDER BY note_id,accession"
            ):
                key = _text(row, "note_id")
                links[key] = (*links.get(key, ()), _text(row, "accession"))
        return links

    def latest_brief(
        self, settings: PulseSettings | None = None, *, demo: bool = False
    ) -> Brief | None:
        """Return the newest snapshot compatible with the requested profile and mode.

        Args:
            settings: Optional exact profile to match, including feed settings.
            demo: Whether to choose synthetic snapshots instead of live evidence.

        Returns:
            The latest compatible saved brief, or None before a matching run.
        """
        with self._connect() as connection:
            for row in connection.execute(
                "SELECT payload FROM briefs ORDER BY timestamp DESC,key"
            ):
                brief = Brief.model_validate_json(_text(row, "payload"))
                if brief.demo == demo and (
                    settings is None or brief.settings == settings
                ):
                    return brief
        return None

    def list_briefs(self, *, limit: int | None = 100) -> tuple[Brief, ...]:
        """Return reproducible brief snapshots, including explicitly labeled demos."""
        return self._read_models(
            Brief,
            "SELECT payload FROM briefs ORDER BY timestamp DESC,key LIMIT ?",
            (_row_limit(limit),),
        )
