# src/sec_nlp/cli/commands/clean.py
"""Workspace cleanup CLI commands."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import CliPositionalArg

from sec_nlp.core.infra.logger import (
    bullet_line,
    error,
    format_path,
    format_size,
    info_line,
    logger,
    styled_header,
    success,
    warning,
)
from sec_nlp.core.infra.settings import PROJECT_ROOT


class Clean(BaseModel):
    """Clear workspace directories such as downloads, outputs, and logs."""

    model_config = ConfigDict(
        defer_build=True,
        frozen=True,
    )

    target: CliPositionalArg[Literal["all", "downloads", "outputs", "logs"]] = (
        Field(
            default="all",
            description="Which path to clear: 'all', 'downloads', 'outputs', or 'logs'",
        )
    )

    root: Path = Field(
        default=PROJECT_ROOT,
        description="Base directory containing downloads/outputs/logs",
    )

    downloads_path: Path | None = Field(
        default=None,
        description="Override downloads directory (defaults to <root>/downloads)",
    )

    outputs_path: Path | None = Field(
        default=None,
        description="Override outputs directory (defaults to <root>/outputs)",
    )

    logs_path: Path | None = Field(
        default=None,
        description="Override logs directory (defaults to <root>/logs)",
    )

    dry_run: bool = Field(
        default=False,
        description="Show what would be deleted without actually deleting",
    )

    force: bool = Field(
        default=False,
        description="Skip confirmation prompt",
        json_schema_extra={"cli_args": {"aliases": ["-f"]}},
    )

    def cli_cmd(self) -> None:
        """Execute cleanup based on the selected target."""
        targets = self._get_targets()

        title = "Workspace Cleanup" + (" [DRY RUN]" if self.dry_run else "")
        logger.info(styled_header(title))

        target_descriptions: list[str] = [name for name, _ in targets]
        logger.info(bullet_line("Targets", ", ".join(target_descriptions)))
        logger.info(bullet_line("Root", format_path(self.root.resolve())))

        if self.dry_run:
            logger.info(warning("\nDry run mode - no changes will be made"))
        elif not self.force:
            logger.warning(
                warning(
                    "\nThis will delete files in the paths above and recreate empty folders."
                )
            )
            logger.warning(
                info_line("Use --force to skip this prompt", dim=True)
            )
            try:
                response = input("Continue? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                logger.info("\nAborted.")
                return

            if response not in ("y", "yes"):
                logger.info("Aborted.")
                return

        # Track statistics
        total_size = 0
        total_files = 0

        for name, path in targets:
            size, files = self._clear_path(name, path)
            total_size += size
            total_files += files

        # Show summary
        if not self.dry_run and targets:
            logger.info(
                "\n"
                + bullet_line(
                    "Summary",
                    f"Freed {format_size(total_size)}, removed {total_files:,} files",
                    color="cyan",
                )
            )

    def _get_targets(self) -> list[tuple[str, Path]]:
        """Resolve the paths to clear based on the target selection."""
        mapping = {
            "downloads": self.downloads_path or (self.root / "downloads"),
            "outputs": self.outputs_path or (self.root / "outputs"),
            "logs": self.logs_path or (self.root / "logs"),
        }

        if self.target == "all":
            return list(mapping.items())

        return [(self.target, mapping[self.target])]

    def _clear_path(self, name: str, path: Path) -> tuple[int, int]:
        """Remove and recreate a directory (or remove a file path).

        Returns:
            Tuple of (total_size_freed, total_files_deleted)
        """
        try:
            if not path.exists():
                if self.dry_run:
                    logger.info(info_line(f"{name} does not exist", dim=True))
                else:
                    path.mkdir(parents=True, exist_ok=True)
                    logger.info(
                        info_line(
                            f"{name} already empty (created {format_path(path)})",
                            dim=True,
                        )
                    )
                return 0, 0

            # Calculate size before deletion
            total_size = 0
            total_files = 0

            if path.is_file() or path.is_symlink():
                total_size = path.stat().st_size
                total_files = 1
            else:
                for item in path.rglob("*"):
                    if item.is_file():
                        total_size += item.stat().st_size
                        total_files += 1

            if self.dry_run:
                logger.info(
                    info_line(
                        f"Would clear {name}: {format_size(total_size)}, {total_files:,} files"
                    )
                )
            else:
                if path.is_file() or path.is_symlink():
                    path.unlink()
                else:
                    shutil.rmtree(path)

                path.mkdir(parents=True, exist_ok=True)
                logger.info(
                    success(
                        f"Cleared {name} at {format_path(path)}: {format_size(total_size)}"
                    )
                )

            return total_size, total_files

        except OSError as exc:
            logger.error(
                error(f"Failed to clear {name} at {format_path(path)}: {exc}")
            )
            return 0, 0
