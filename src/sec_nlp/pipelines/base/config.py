# src/sec_nlp/pipelines/base/config.py
"""Frozen base settings shared by every pipeline preset.

All pipeline configs inherit from ``BasePipelineSettings``, which layers
Pydantic settings (CLI → env → .env) on top of common fields: symbols, date
range, filing mode, run identifiers, and output paths. The class also handles
run-registry bookkeeping (register on init, mark complete via
``complete_run``) and provides convenience properties for run metadata.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.utils import is_valid_email
from sec_nlp.types import (
    ConfigValue,
    InitSubclassKwargs,
    JsonDict,
    JsonObject,
    JsonValue,
)

_CLASSVAR_UNSET = "__UNSET__"


class BasePipelineSettings(BaseSettings, ABC):
    """Frozen base settings shared by every pipeline preset.

    Configuration values are resolved in descending precedence:
    CLI arguments → environment variables → ``.env`` file → field defaults.
    Subclasses must set ``pipeline_type`` and implement ``pipeline_label()``.
    The model registers each run in the SQLite run registry at init time and
    exposes ``complete_run()`` for status/metadata recording.
    """

    pipeline_type: ClassVar[str] = _CLASSVAR_UNSET
    symbols_optional: ClassVar[bool] = False

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        arbitrary_types_allowed=True,
        validation_error_cause=True,
        cli_exit_on_error=True,
        cli_implicit_flags=True,
        nested_model_default_partial_update=True,
        case_sensitive=False,
        defer_build=True,
        frozen=True,
    )

    email: str = Field(
        default="nrhill1@gmail.com",
        description="Email address for SEC EDGAR requests (required by SEC)",
    )

    verbose: bool = Field(
        default=False,
        description="Enable verbose (DEBUG) logger",
    )
    log_format: Literal["simple", "detailed", "json"] = Field(
        default="simple",
        description="Log output format",
    )
    log_file: Path | None = Field(
        default=None,
        description="Write logs to file instead of console",
    )

    # Run specific
    fresh: bool = Field(
        default=False,
        description="Clear download and output folders prior to run",
    )
    incremental: bool = Field(
        default=True,
        description="Enable incremental processing - skip accessions that have already been processed",
    )
    cleanup: bool = Field(
        default=True,
        description="Clean up downloaded files after processing",
    )

    # Run embedding
    dry_run: bool = Field(
        default=True,
        description="Run without performing any embedding",
    )

    # Run identifiers (run_id is public; timestamp is private)
    run_id: UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique run identifier (UUID, always present)",
    )
    _run_timestamp: datetime = PrivateAttr(
        default_factory=lambda: datetime.now(UTC)
    )
    # Mutable container so frozen model can update without object.__setattr__
    _short_id_ref: dict[str, int] = PrivateAttr(
        default_factory=lambda: {"value": 0}
    )
    _profiling_metadata: JsonDict = PrivateAttr(default_factory=dict)

    # Data paths
    dl_path: Path = Field(
        default=Path("./downloads"),
        description="Path for downloading SEC filings",
    )
    out_path: Path = Field(
        default=Path("./outputs"),
        description="Path for output files",
    )

    # Filing search parameters
    symbols: list[str] = Field(
        default=["AAPL", "TSLA", "MSFT"],
        description="List of ticker symbols to search for",
    )
    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Filing mode (annual, quarterly, current, proxy, holdings, insider, registration, shelf)",
    )
    forms: list[str] | None = Field(
        default=None,
        description="SEC form types to search (e.g., ['10-K', '10-Q', '8-K', '6-K']). Overrides mode if specified.",
    )
    start_date: date | None = Field(
        default=None,
        description="Start date for filing search (YYYY-MM-DD)",
    )
    end_date: date | None = Field(
        default=None,
        description="End date for filing search (YYYY-MM-DD)",
    )

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: InitSubclassKwargs) -> None:
        """Enforce ``pipeline_type`` ClassVar and ``frozen=True`` on every subclass."""
        super().__pydantic_init_subclass__(**kwargs)

        # Ensure pipeline_type is set
        if cls.pipeline_type == _CLASSVAR_UNSET:
            raise TypeError(f"{cls.__name__} must set 'pipeline_type' ClassVar")

        # Ensure frozen=True is not overridden
        if cls.model_config.get("frozen") is not True:
            raise TypeError(
                f"{cls.__name__} must not override frozen=True from BasePipelineSettings"
            )

    @model_validator(mode="before")
    @classmethod
    def _merge_partial_nested_configs(
        cls,
        values: Mapping[str, ConfigValue | BaseModel] | BaseModel,
    ) -> Mapping[str, ConfigValue | BaseModel] | BaseModel:
        """Merge partial CLI overrides into nested model defaults.

        CLI dotted args (e.g. ``--llm.model-name``) arrive as partial dicts
        that would otherwise replace the entire nested model and drop its
        pipeline-specific defaults. This validator overlays those partials
        onto the full default payload before Pydantic validation.
        """
        if not isinstance(values, Mapping):
            return values

        merged_values: dict[str, ConfigValue | BaseModel] = dict(values)
        for field_name, field_info in cls.model_fields.items():
            raw_value = merged_values.get(field_name)
            if not isinstance(raw_value, Mapping):
                continue

            annotation = field_info.annotation
            if not isinstance(annotation, type):
                continue
            if not issubclass(annotation, BaseModel):
                continue

            default_value = field_info.get_default(call_default_factory=True)
            if not isinstance(default_value, BaseModel):
                continue

            default_payload = default_value.model_dump(mode="python")
            default_payload.update(dict(raw_value))
            merged_values[field_name] = annotation.model_validate(
                default_payload
            )

        return merged_values

    def model_post_init(self, __context: JsonObject | None) -> None:
        """Register this run in the SQLite run registry after config freezes."""
        try:
            from sec_nlp.pipelines.observability.run_registry import (
                get_registry,
            )

            registry = get_registry()
            short_id = registry.register_run(
                run_id=str(self.run_id),
                pipeline_type=self.pipeline_type,
                started_at=self._run_timestamp,
                output_dir=str(self.out_path),
            )
            if short_id is not None:
                self._short_id_ref["value"] = short_id
        except (ImportError, OSError, sqlite3.Error):
            logger.debug("Run registry unavailable during init")

    @abstractmethod
    def pipeline_label(self) -> str:
        """Return a human-readable name for this pipeline."""
        raise NotImplementedError

    @field_validator("start_date", mode="before")
    @classmethod
    def parse_start_date(cls, v: str | date | None) -> date | None:
        """Coerce an ISO-format string into a ``date`` for the start bound."""
        if isinstance(v, str):
            return datetime.strptime(v, "%Y-%m-%d").date()
        return v

    @field_validator("end_date", mode="before")
    @classmethod
    def parse_end_date(cls, v: str | date | None) -> date | None:
        """Coerce an ISO-format string into a ``date`` for the end bound."""
        if isinstance(v, str):
            return datetime.strptime(v, "%Y-%m-%d").date()
        return v

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, v: list[str] | str) -> list[str]:
        """Split comma/space-separated input and uppercase each ticker symbol."""
        if isinstance(v, str):
            v = [part for part in v.replace(",", " ").split() if part]
        return [s.strip().upper() for s in v]

    @field_validator("forms", mode="before")
    @classmethod
    def normalize_forms(cls, v: list[str] | str | None) -> list[str] | None:
        """Normalize form types (e.g. ``10K`` → ``10-K``) and uppercase."""
        if v is None:
            return None
        if isinstance(v, str):
            # Handle comma or space-separated
            v = [part for part in v.replace(",", " ").split() if part]
        # Normalize variants: "10K" -> "10-K", "8k" -> "8-K", "6k" -> "6-K"
        normalized = []
        for form in v:
            form_upper = form.strip().upper()
            # Add hyphens if missing for common forms
            if form_upper in ("10K", "10Q", "8K", "6K"):
                form_upper = form_upper[:-1] + "-" + form_upper[-1]
            normalized.append(form_upper)
        return normalized if normalized else None

    @classmethod
    def _generate_run_id(cls) -> UUID:
        """Generate a fresh UUID4 run identifier."""
        return uuid.uuid4()

    def run_path_component(self) -> str:
        return self._run_timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%S%z")

    @field_validator("run_id", mode="before")
    @classmethod
    def coerce_run_id(cls, v: JsonValue) -> UUID:
        """Coerce string, UUID, or sentinel values into a valid ``UUID``."""
        if v in (None, "", 0, "0"):
            return cls._generate_run_id()
        if isinstance(v, UUID):
            return v
        if isinstance(v, str):
            try:
                return UUID(v)
            except Exception as e:
                raise ValueError("run_id must be a valid UUID") from e
        raise ValueError("run_id must be a valid UUID")

    @field_validator("log_file", mode="after")
    @classmethod
    def validate_log_file(cls, v: Path | None) -> Path | None:
        """Pass through the log file path unchanged."""
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Reject malformed email addresses required by SEC EDGAR."""
        if not is_valid_email(v):
            raise ValueError("Invalid email format")
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        start, end = self.date_range
        if start > end:
            raise ValueError("start_date cannot be after end_date")
        if start < date(2001, 1, 1):
            raise ValueError(
                "start_date cannot be before 1993-01-01 (SEC EDGAR launch)"
            )
        if end > date.today():
            raise ValueError("end_date cannot be in the future")
        return self

    @cached_property
    def date_range(self) -> tuple[date, date]:
        """Compute the effective (start, end) date range, defaulting to ~10 years."""
        today = datetime.today().date()
        ten_years_ago = today - timedelta(days=365 * 10)
        start = self.start_date or ten_years_ago
        end = self.end_date or today
        return start, end

    @property
    def effective_forms(self) -> list[str]:
        """Get the effective list of SEC forms to process.

        Returns forms if specified, otherwise derives from mode.
        """
        if self.forms is not None:
            return self.forms
        return list(self.mode.forms)

    def setup_paths(self) -> None:
        """Create base output/download directories and optional log parent.

        Symbol-specific output directories are created lazily only when a stage
        actually writes output artifacts.
        """

        if self.fresh:
            self._fresh()

        self.out_path.mkdir(parents=True, exist_ok=True)
        self.dl_path.mkdir(parents=True, exist_ok=True)
        if self.log_file is not None:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def get_symbol_output_dir(self, symbol: str) -> Path:
        """Return (and create) the run-scoped output dir for *symbol*.

        Returns:
            ``<out_path>/<run_timestamp>/<pipeline_type>/<SYMBOL>``
        """
        normalized_symbol = symbol.strip().upper()
        run_component = self.run_path_component()
        symbol_out_path = (
            self.out_path
            / run_component
            / self.pipeline_type
            / normalized_symbol
        )
        symbol_out_path.mkdir(parents=True, exist_ok=True)
        return symbol_out_path

    def summary(self) -> str:
        """Return a human-readable multi-line config summary for logging."""
        start, end = self.date_range
        days = (end - start).days
        forms_display = ", ".join(self.effective_forms)

        lines = [
            f"Pipeline: {self.pipeline_type}",
            f"Symbols: {', '.join(self.symbols)}",
            f"Forms: {forms_display}",
            f"Date Range: {start} to {end} ({days} days)",
            f"Downloads: {self.dl_path}",
            f"Outputs: {self.out_path}",
            f"Dry Run: {self.dry_run}",
        ]

        return "\n".join(lines)

    def print_summary(self) -> None:
        """Log each line of the config summary at INFO level."""
        logger.info("Configuration Summary:")
        for line in self.summary().split("\n"):
            logger.info("  %s", line)

    @property
    def short_id(self) -> int:
        """Get the short sequential run ID (e.g., 42)."""
        self._ensure_short_id()
        return self._short_id_ref["value"]

    @property
    def short_id_display(self) -> str:
        """Get the short ID for display (e.g., '#42')."""
        self._ensure_short_id()
        sid = self._short_id_ref["value"]
        return f"#{sid}" if sid else str(self.run_id)

    def _ensure_short_id(self) -> None:
        """Lazily resolve the sequential short ID from the run registry."""
        if self._short_id_ref["value"]:
            return
        try:
            from sec_nlp.pipelines.observability.run_registry import (
                get_registry,
            )

            registry = get_registry()
            existing = registry.get_run(str(self.run_id))
            if existing is not None:
                self._short_id_ref["value"] = existing.record_id
                return

            short_id = registry.register_run(
                run_id=str(self.run_id),
                pipeline_type=self.pipeline_type,
                started_at=self._run_timestamp,
                output_dir=str(self.out_path),
            )
            if short_id is not None:
                self._short_id_ref["value"] = short_id
        except (ImportError, OSError, sqlite3.Error):
            logger.debug("Run registry unavailable for short_id lookup")
            return

    @property
    def run_timestamp(self) -> datetime:
        """Get the run start timestamp (UTC)."""
        return self._run_timestamp

    def complete_run(
        self,
        success: bool = True,
        metadata: str | JsonDict | None = None,
    ) -> None:
        """Mark this run as completed in the SQLite run registry.

        Args:
            success: Whether the run succeeded.
            metadata: Optional JSON string or dict persisted alongside the run record.
        """
        self._prune_empty_output_dirs()
        try:
            from sec_nlp.pipelines.observability.run_registry import (
                get_registry,
            )

            registry = get_registry()
            merged_metadata: JsonDict | None = None
            if isinstance(metadata, dict):
                merged_metadata = {}
                for key, value in metadata.items():
                    merged_metadata[str(key)] = value
            elif metadata is None and self._profiling_metadata:
                merged_metadata = {}
                merged_metadata["profiling"] = dict(self._profiling_metadata)

            if (
                merged_metadata is not None
                and self._profiling_metadata
                and isinstance(merged_metadata, dict)
                and "profiling" not in merged_metadata
            ):
                merged_metadata["profiling"] = self._profiling_metadata

            serialized_metadata: str | None = None
            if merged_metadata is not None:
                serialized_metadata = json.dumps(merged_metadata)
            elif isinstance(metadata, str):
                serialized_metadata = metadata

            registry.complete_run(
                run_id=str(self.run_id),
                success=success,
                metadata=serialized_metadata,
            )
        except (ImportError, OSError, sqlite3.Error):
            logger.debug("Run registry unavailable for run completion")

    def _prune_empty_output_dirs(self) -> None:
        """Remove empty symbol/run output directories created during no-output runs."""
        pipeline_output_root = (
            self.out_path / self.run_path_component() / self.pipeline_type
        )
        if not pipeline_output_root.exists():
            return
        if not pipeline_output_root.is_dir():
            return

        child_dirs = sorted(
            (path for path in pipeline_output_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in child_dirs:
            self._remove_dir_if_empty(directory)

        self._remove_dir_if_empty(pipeline_output_root)
        self._remove_dir_if_empty(pipeline_output_root.parent)

    @staticmethod
    def _remove_dir_if_empty(path: Path) -> None:
        """Remove ``path`` if it exists and has no children."""
        if not path.exists() or not path.is_dir():
            return
        try:
            next(path.iterdir())
            return
        except StopIteration:
            path.rmdir()
        except OSError:
            logger.debug(
                "Could not remove non-empty output directory: %s",
                path,
            )

    @property
    def num_symbols(self) -> int:
        """Get number of symbols to process."""
        return len(self.symbols)

    @property
    def date_range_days(self) -> int:
        """Get number of days in date range."""
        start, end = self.date_range
        return (end - start).days

    def _fresh(self) -> None:
        """Remove existing download and output directories before a fresh run."""
        import shutil

        logger.info(
            "Removing outputs at %s",
            self.out_path.resolve(),
        )
        logger.info(
            "Removing downloads at %s",
            self.dl_path.resolve(),
        )
        if self.out_path.exists():
            shutil.rmtree(self.out_path)
        if self.dl_path.exists():
            shutil.rmtree(self.dl_path)

    def get_date_range(self) -> tuple[date, date]:
        """Return the computed (start, end) date range."""
        return self.date_range

    def get_log_level(self) -> str:
        """Apply verbose/default log level to the package logger and return the name."""
        level = logging.DEBUG if self.verbose else logging.INFO
        logger.setLevel(level)
        return logging.getLevelName(level)

    def __repr__(self) -> str:
        """Return a concise debug representation of pipeline settings."""
        return f"<{self.__class__.__name__} type={self.pipeline_type}>"
