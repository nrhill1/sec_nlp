# src/sec_nlp/pipelines/observability/run_registry.py
"""SQLite-based registry for tracking pipeline runs with short sequential IDs."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.settings import PROJECT_ROOT
from sec_nlp.pipelines.types import QueryParam


class RunRecordDict(TypedDict):
    """Normalized run record persisted in the run registry."""

    record_id: int
    short_id: str
    run_id: str
    pipeline_type: str
    started_at: str | None
    completed_at: str | None
    status: str
    output_dir: str | None
    duration_seconds: float | None


# Default location for the run registry database
_REGISTRY_DIR: Path = (PROJECT_ROOT / ".cache" / "sec-nlp").resolve()
DEFAULT_REGISTRY_PATH: Path = _REGISTRY_DIR / "runs.db"


@dataclass(frozen=True)
class RunRecord:
    """A single pipeline run record."""

    record_id: int
    run_id: str
    pipeline_type: str
    started_at: datetime
    completed_at: datetime | None
    status: str  # "running", "completed", "failed"
    output_dir: str | None
    metadata: str | None  # JSON string

    @property
    def short_id(self) -> str:
        """Get short display ID (e.g., '#42')."""
        return f"#{self.record_id}"

    @property
    def duration_seconds(self) -> float | None:
        """Get run duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> RunRecordDict:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "short_id": self.short_id,
            "run_id": self.run_id,
            "pipeline_type": self.pipeline_type,
            "started_at": self.started_at.isoformat()
            if self.started_at
            else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "status": self.status,
            "output_dir": self.output_dir,
            "duration_seconds": self.duration_seconds,
        }


class RunRegistry:
    """SQLite-based registry for pipeline runs."""

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the registry.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.cache/sec-nlp/runs.db
        """
        self.db_path = (
            Path(db_path) if db_path else DEFAULT_REGISTRY_PATH
        ).resolve()
        db_dir = Path(os.path.dirname(os.fspath(self.db_path)))
        db_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT UNIQUE NOT NULL,
                    pipeline_type TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'running',
                    output_dir TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_pipeline_type
                ON runs(pipeline_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_started_at
                ON runs(started_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_status
                ON runs(status)
            """)

    def register_run(
        self,
        run_id: str,
        pipeline_type: str,
        started_at: datetime | None = None,
        output_dir: str | None = None,
    ) -> int | None:
        """Register a new pipeline run.

        Args:
            run_id: Unique run identifier (from config.run_id)
            pipeline_type: Type of pipeline (e.g., 'exhibit')
            started_at: Start timestamp (defaults to now UTC)
            output_dir: Output directory path

        Returns:
            The sequential run ID (short ID)
        """
        started_at = started_at or datetime.now(UTC)

        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (run_id, pipeline_type, started_at, status, output_dir)
                VALUES (?, ?, ?, 'running', ?)
                """,
                (run_id, pipeline_type, started_at, output_dir),
            )
            short_id = cursor.lastrowid

        logger.debug("Registered run #%d (%s)", short_id, run_id)
        return short_id

    def complete_run(
        self,
        run_id: str,
        success: bool = True,
        metadata: str | None = None,
    ) -> None:
        """Mark a run as completed.

        Args:
            run_id: The run_id to complete
            success: Whether the run succeeded
            metadata: Optional JSON metadata string
        """
        status = "completed" if success else "failed"
        completed_at = datetime.now(UTC)

        with self._connection() as conn:
            conn.execute(
                """
                UPDATE runs
                SET completed_at = ?, status = ?, metadata = ?
                WHERE run_id = ?
                """,
                (completed_at, status, metadata, run_id),
            )

    def get_run(self, identifier: int | str) -> RunRecord | None:
        """Get a run by short ID (int) or run_id (str).

        Args:
            identifier: Either the short numeric ID or full run_id string

        Returns:
            RunRecord if found, None otherwise
        """
        with self._connection() as conn:
            if isinstance(identifier, int):
                row = conn.execute(
                    "SELECT * FROM runs WHERE id = ?", (identifier,)
                ).fetchone()
            else:
                # Try as short ID first (e.g., "#42" or "42")
                clean_id = str(identifier).lstrip("#")
                if clean_id.isdigit():
                    row = conn.execute(
                        "SELECT * FROM runs WHERE id = ?", (int(clean_id),)
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT * FROM runs WHERE run_id = ?", (identifier,)
                    ).fetchone()

            if row:
                return self._row_to_record(row)
            return None

    def list_runs(
        self,
        pipeline_type: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[RunRecord]:
        """List runs with optional filtering.

        Args:
            pipeline_type: Filter by pipeline type
            status: Filter by status ('running', 'completed', 'failed')
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of RunRecord objects
        """
        query = "SELECT * FROM runs WHERE 1=1"
        params: list[QueryParam] = []

        if pipeline_type:
            query += " AND pipeline_type = ?"
            params.append(pipeline_type)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_record(row) for row in rows]

    def delete_run(self, identifier: int | str) -> bool:
        """Delete a run record.

        Args:
            identifier: Short ID or run_id

        Returns:
            True if deleted, False if not found
        """
        run = self.get_run(identifier)
        if not run:
            return False

        with self._connection() as conn:
            conn.execute("DELETE FROM runs WHERE id = ?", (run.record_id,))

        logger.debug("Deleted run #%d", run.record_id)
        return True

    def prune_runs(
        self,
        older_than_days: int | None = None,
        keep_last: int | None = None,
        pipeline_type: str | None = None,
    ) -> int:
        """Prune old run records.

        Args:
            older_than_days: Delete runs older than this many days
            keep_last: Keep the last N runs (per pipeline type if specified)
            pipeline_type: Only prune runs of this type

        Returns:
            Number of runs deleted
        """
        deleted = 0

        with self._connection() as conn:
            if older_than_days is not None:
                cutoff = datetime.now(UTC).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                cutoff = cutoff - timedelta(days=older_than_days)

                query = "DELETE FROM runs WHERE started_at < ?"
                params: list[QueryParam] = [cutoff]

                if pipeline_type:
                    query += " AND pipeline_type = ?"
                    params.append(pipeline_type)

                cursor = conn.execute(query, params)
                deleted += cursor.rowcount

            if keep_last is not None:
                # Get IDs to keep
                if pipeline_type:
                    keep_query = """
                        SELECT id FROM runs
                        WHERE pipeline_type = ?
                        ORDER BY id DESC LIMIT ?
                    """
                    keep_ids = [
                        row["id"]
                        for row in conn.execute(
                            keep_query, (pipeline_type, keep_last)
                        ).fetchall()
                    ]

                    if keep_ids:
                        placeholders = ",".join("?" * len(keep_ids))
                        delete_query = f"""
                            DELETE FROM runs
                            WHERE pipeline_type = ? AND id NOT IN ({placeholders})
                        """
                        cursor = conn.execute(
                            delete_query, [pipeline_type, *keep_ids]
                        )
                        deleted += cursor.rowcount
                else:
                    # Keep last N overall
                    keep_query = "SELECT id FROM runs ORDER BY id DESC LIMIT ?"
                    keep_ids = [
                        row["id"]
                        for row in conn.execute(
                            keep_query, (keep_last,)
                        ).fetchall()
                    ]

                    if keep_ids:
                        placeholders = ",".join("?" * len(keep_ids))
                        delete_query = (
                            f"DELETE FROM runs WHERE id NOT IN ({placeholders})"
                        )
                        cursor = conn.execute(delete_query, keep_ids)
                        deleted += cursor.rowcount

        return deleted

    def get_stats(self) -> dict[str, int | dict[str, int] | str]:
        """Get registry statistics.

        Returns:
            Dictionary with stats
        """
        with self._connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

            by_status = {}
            for row in conn.execute(
                "SELECT status, COUNT(*) as cnt FROM runs GROUP BY status"
            ).fetchall():
                by_status[row["status"]] = row["cnt"]

            by_pipeline = {}
            for row in conn.execute(
                "SELECT pipeline_type, COUNT(*) as cnt FROM runs GROUP BY pipeline_type"
            ).fetchall():
                by_pipeline[row["pipeline_type"]] = row["cnt"]

            return {
                "total_runs": total,
                "by_status": by_status,
                "by_pipeline": by_pipeline,
                "db_path": str(self.db_path),
            }

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RunRecord:
        """Convert a database row to a RunRecord."""
        return RunRecord(
            record_id=row["id"],
            run_id=row["run_id"],
            pipeline_type=row["pipeline_type"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            status=row["status"],
            output_dir=row["output_dir"],
            metadata=row["metadata"],
        )


# Global registry instance (lazy-loaded)
_registry: RunRegistry | None = None


def get_registry() -> RunRegistry:
    """Get the global run registry instance."""
    global _registry
    if _registry is None:
        _registry = RunRegistry()
    return _registry
