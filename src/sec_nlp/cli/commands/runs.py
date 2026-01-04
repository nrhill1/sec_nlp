# src/sec_nlp/cli/commands/runs.py
"""CLI commands for managing pipeline runs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import CliSubCommand, SettingsConfigDict

from sec_nlp.core.infra.logger import (
    bullet_line,
    color_text,
    logger,
    styled_header,
)
from sec_nlp.pipelines.observability.run_registry import get_registry


def _format_local(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
    """Format a datetime in the local timezone."""
    if dt is None:
        return "—"
    local_tz = datetime.now().astimezone().tzinfo
    try:
        local_dt = dt if dt.tzinfo is None else dt.astimezone(local_tz)
    except Exception:
        local_dt = dt
    return local_dt.strftime(fmt)


class RunsLs(BaseModel):
    """List pipeline runs."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    pipeline: str | None = Field(
        default=None,
        description="Filter by pipeline type (e.g., exhibit10, warranty)",
    )
    status: Literal["running", "completed", "failed"] | None = Field(
        default=None,
        description="Filter by status",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of runs to show",
    )

    def cli_cmd(self) -> None:
        """List pipeline runs."""
        logger.info(styled_header("Pipeline Runs"))

        registry = get_registry()
        runs = registry.list_runs(
            pipeline_type=self.pipeline,
            status=self.status,
            limit=self.limit,
        )

        if not runs:
            logger.info(color_text("No runs found.", color="yellow"))
            return

        # Display runs
        for run in runs:
            # Derive a display status so stale records with a completed_at
            # timestamp don't still render as "running", and mark
            # non-completed runs as "incomplete".
            if run.status == "running" and run.completed_at is None:
                display_status = "incomplete"
            elif run.completed_at and run.status == "running":
                display_status = "completed"
            else:
                display_status = run.status
            status_color = {
                "running": "yellow",
                "completed": "green",
                "failed": "red",
                "incomplete": "dim",
            }.get(display_status, "dim")

            # Format duration
            duration_str = ""
            if run.duration_seconds is not None:
                mins, secs = divmod(int(run.duration_seconds), 60)
                if mins > 0:
                    duration_str = f" ({mins}m {secs}s)"
                else:
                    duration_str = f" ({secs}s)"

            logger.info(
                "  %s  %s  %s  %s%s",
                color_text(run.short_id.ljust(6), color="cyan"),
                color_text(run.pipeline_type.ljust(12), color="blue"),
                color_text(display_status.ljust(10), color=status_color),
                _format_local(run.started_at),
                duration_str,
            )

        logger.info("")
        logger.info(color_text(f"Showing {len(runs)} run(s)", color="dim"))


class RunsInfo(BaseModel):
    """Show detailed information about a run."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    run: str = Field(
        description="Run ID (e.g., #42, 42, or full run_id)",
    )

    def cli_cmd(self) -> None:
        """Show run details."""
        registry = get_registry()
        run = registry.get_run(self.run)

        if not run:
            logger.error(
                color_text(f"Run '{self.run}' not found.", color="red")
            )
            return

        logger.info(styled_header(f"Run {run.short_id}"))
        logger.info(bullet_line("Run ID", run.run_id))
        logger.info(bullet_line("Pipeline", run.pipeline_type))
        logger.info(bullet_line("Status", run.status))
        logger.info(
            bullet_line(
                "Started", _format_local(run.started_at, "%Y-%m-%d %H:%M:%S %Z")
            )
        )
        if run.completed_at:
            logger.info(
                bullet_line(
                    "Completed",
                    _format_local(run.completed_at, "%Y-%m-%d %H:%M:%S %Z"),
                )
            )
        if run.duration_seconds is not None:
            mins, secs = divmod(int(run.duration_seconds), 60)
            logger.info(bullet_line("Duration", f"{mins}m {secs}s"))
        if run.output_dir:
            logger.info(bullet_line("Output Dir", run.output_dir))


class RunsDelete(BaseModel):
    """Delete a run record."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    run: str = Field(
        description="Run ID to delete (e.g., #42, 42, or full run_id)",
    )
    force: bool = Field(
        default=False,
        description="Skip confirmation",
        json_schema_extra={"cli_args": {"aliases": ["-f"]}},
    )

    def cli_cmd(self) -> None:
        """Delete a run record."""
        registry = get_registry()
        run = registry.get_run(self.run)

        if not run:
            logger.error(
                color_text(f"Run '{self.run}' not found.", color="red")
            )
            return

        if not self.force:
            logger.warning(
                color_text(
                    f"This will delete run {run.short_id} ({run.run_id}).",
                    color="yellow",
                )
            )
            try:
                response = input("Continue? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                logger.info("\nAborted.")
                return

            if response not in ("y", "yes"):
                logger.info("Aborted.")
                return

        if registry.delete_run(run.record_id):
            logger.info(
                color_text(f"✓ Deleted run {run.short_id}", color="green")
            )
        else:
            logger.error(color_text("Failed to delete run.", color="red"))


class RunsPrune(BaseModel):
    """Prune old run records."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    older_than: int | None = Field(
        default=None,
        ge=1,
        description="Delete runs older than N days",
    )
    keep_last: int | None = Field(
        default=None,
        ge=1,
        description="Keep only the last N runs",
    )
    pipeline: str | None = Field(
        default=None,
        description="Only prune runs of this pipeline type",
    )
    force: bool = Field(
        default=False,
        description="Skip confirmation",
        json_schema_extra={"cli_args": {"aliases": ["-f"]}},
    )

    def cli_cmd(self) -> None:
        """Prune old run records."""
        if self.older_than is None and self.keep_last is None:
            logger.error(
                color_text(
                    "Specify --older-than or --keep-last to prune runs.",
                    color="red",
                )
            )
            return

        registry = get_registry()

        if not self.force:
            msg = "This will delete"
            if self.older_than:
                msg += f" runs older than {self.older_than} days"
            if self.keep_last:
                if self.older_than:
                    msg += " and"
                msg += f" runs beyond the last {self.keep_last}"
            if self.pipeline:
                msg += f" (pipeline: {self.pipeline})"

            logger.warning(color_text(msg + ".", color="yellow"))
            try:
                response = input("Continue? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                logger.info("\nAborted.")
                return

            if response not in ("y", "yes"):
                logger.info("Aborted.")
                return

        deleted = registry.prune_runs(
            older_than_days=self.older_than,
            keep_last=self.keep_last,
            pipeline_type=self.pipeline,
        )

        logger.info(color_text(f"✓ Pruned {deleted} run(s)", color="green"))


class RunsStats(BaseModel):
    """Show run registry statistics."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    def cli_cmd(self) -> None:
        """Show registry statistics."""
        registry = get_registry()
        stats = registry.get_stats()

        logger.info(styled_header("Run Registry Stats"))
        db_path = stats.get("db_path", "")
        logger.info(bullet_line("Database", str(db_path) if db_path else None))
        logger.info(bullet_line("Total runs", str(stats.get("total_runs", 0))))

        by_status = stats.get("by_status")
        if by_status and isinstance(by_status, dict):
            logger.info("")
            logger.info(color_text("By Status:", color="cyan"))
            for status, count in sorted(by_status.items()):
                logger.info(f"  {status}: {count}")

        by_pipeline = stats.get("by_pipeline")
        if by_pipeline and isinstance(by_pipeline, dict):
            logger.info("")
            logger.info(color_text("By Pipeline:", color="cyan"))
            for pipeline, count in sorted(by_pipeline.items()):
                logger.info(f"  {pipeline}: {count}")


class Runs(BaseModel):
    """Manage pipeline runs (ls, info, delete, prune)."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    ls: CliSubCommand[RunsLs] = Field(
        description="List pipeline runs",
    )
    info: CliSubCommand[RunsInfo] = Field(
        description="Show details of a specific run",
    )
    delete: CliSubCommand[RunsDelete] = Field(
        description="Delete a run record",
    )
    prune: CliSubCommand[RunsPrune] = Field(
        description="Prune old run records",
    )
    stats: CliSubCommand[RunsStats] = Field(
        description="Show run registry statistics",
    )

    def cli_cmd(self) -> None:
        """Execute runs subcommand."""
        from pydantic_settings import CliApp

        CliApp.run_subcommand(self)
