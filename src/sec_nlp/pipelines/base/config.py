# src/sec_nlp/pipelines/base/config.py
"""Base configuration for pipelines."""

from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Literal, Self
from uuid import UUID

from pydantic import Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.utils import is_valid_email
from sec_nlp.types import InitSubclassKwargs, JsonDict, JsonObject, JsonValue

_CLASSVAR_UNSET = "__UNSET__"


class BasePipelineSettings(BaseSettings, ABC):
    """Base config type for all pipelines.

    Configuration is loaded from (in order of precedence):
    1. Command-line arguments (highest)
    2. Environment variables
    3. .env file
    """

    pipeline_type: ClassVar[str] = _CLASSVAR_UNSET

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
    _short_id: int = PrivateAttr(default=0)  # Sequential ID from registry
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
        description="Filing type: annual (10-K) or quarterly (10-Q)",
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
        """Ensure pipeline_type is set and frozen=True is not overridden."""
        super().__pydantic_init_subclass__(**kwargs)

        # Ensure pipeline_type is set
        if cls.pipeline_type == _CLASSVAR_UNSET:
            raise TypeError(f"{cls.__name__} must set 'pipeline_type' ClassVar")

        # Ensure frozen=True is not overridden
        if cls.model_config.get("frozen") is not True:
            raise TypeError(
                f"{cls.__name__} must not override frozen=True from BasePipelineSettings"
            )

    def model_post_init(self, __context: JsonObject | None) -> None:
        """Register the run after validation completes."""
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
                self._short_id = short_id
        except Exception:
            # Don't fail if registry is unavailable
            pass

    @abstractmethod
    def pipeline_label(self) -> str:
        """Return a human-readable name for this pipeline."""
        raise NotImplementedError

    @field_validator("start_date", mode="before")
    @classmethod
    def parse_start_date(cls, v: str | date | None) -> date | None:
        """Parse start_date from string to date."""
        if isinstance(v, str):
            return datetime.strptime(v, "%Y-%m-%d").date()
        return v

    @field_validator("end_date", mode="before")
    @classmethod
    def parse_end_date(cls, v: str | date | None) -> date | None:
        """Parse start_date from string to date."""
        if isinstance(v, str):
            return datetime.strptime(v, "%Y-%m-%d").date()
        return v

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, v: list[str] | str) -> list[str]:
        """Normalize symbols to uppercase."""
        if isinstance(v, str):
            v = [part for part in v.replace(",", " ").split() if part]
        return [s.strip().upper() for s in v]

    @classmethod
    def _generate_run_id(cls) -> UUID:
        return uuid.uuid4()

    def run_path_component(self) -> str:
        return self._run_timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%S%z")

    @field_validator("run_id", mode="before")
    @classmethod
    def coerce_run_id(cls, v: JsonValue) -> UUID:
        """Ensure run_id is a valid UUID."""
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
        """Return log file path without side effects."""
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
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
        """
        Get computed date range as a tuple[start, end] (cached).
        Defaults to ~10 years ago through today for broader history coverage.
        """
        today = datetime.today().date()
        ten_years_ago = today - timedelta(days=365 * 10)
        start = self.start_date or ten_years_ago
        end = self.end_date or today
        return start, end

    def setup_paths(self) -> None:
        """
        Create output and download directories if they don't exist.
        Clear directory contents if self.fresh=True

        Note: Downloads use a flat structure (sec_edgar_downloader creates its own
        sec-edgar-filings/SYMBOL/FORM_TYPE/ hierarchy inside dl_path).
        Outputs use run-scoped subdirectories for organization
        (e.g., outputs/<run_timestamp>/warranty/AAPL).
        """

        if self.fresh:
            self._fresh()

        self.out_path.mkdir(parents=True, exist_ok=True)
        self.dl_path.mkdir(parents=True, exist_ok=True)
        if self.log_file is not None:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create per-symbol output directories
        for symbol in self.symbols:
            self.get_symbol_output_dir(symbol)

    def get_symbol_output_dir(self, symbol: str) -> Path:
        """
        Get (and create) the output directory for a symbol scoped to the pipeline
        and run.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Path in the form <out_path>/<run_timestamp>/<pipeline_type>/<SYMBOL>
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
        """Get human-readable summary of configuration."""
        start, end = self.date_range
        days = (end - start).days

        lines = [
            f"Pipeline: {self.pipeline_type}",
            f"Symbols: {', '.join(self.symbols)}",
            f"Mode: {self.mode.value} ({self.mode.form})",
            f"Date Range: {start} to {end} ({days} days)",
            f"Downloads: {self.dl_path}",
            f"Outputs: {self.out_path}",
            f"Dry Run: {self.dry_run}",
        ]

        return "\n".join(lines)

    def print_summary(self) -> None:
        """Print configuration summary to logger."""
        logger.info("Configuration Summary:")
        for line in self.summary().split("\n"):
            logger.info("  %s", line)

    @property
    def short_id(self) -> int:
        """Get the short sequential run ID (e.g., 42)."""
        return self._short_id

    @property
    def short_id_display(self) -> str:
        """Get the short ID for display (e.g., '#42')."""
        return f"#{self._short_id}" if self._short_id else str(self.run_id)

    @property
    def run_timestamp(self) -> datetime:
        """Get the run start timestamp (UTC)."""
        return self._run_timestamp

    def complete_run(
        self,
        success: bool = True,
        metadata: str | JsonDict | None = None,
    ) -> None:
        """Mark this run as completed in the registry.

        Args:
            success: Whether the run succeeded
            metadata: Optional JSON metadata string or metadata mapping
        """
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
        except Exception:
            # Don't fail if registry is unavailable
            pass

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
        """Delete old download and output directories"""
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
        """Return the date range as a tuple[start, end]"""
        return self.date_range

    def get_log_level(self) -> str:
        """Get log level string and apply it to the package logger."""
        level = logging.DEBUG if self.verbose else logging.INFO
        logger.setLevel(level)
        return logging.getLevelName(level)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.pipeline_type}>"
