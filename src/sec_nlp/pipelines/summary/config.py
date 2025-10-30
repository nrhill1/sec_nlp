# src/sec_nlp/pipelines/summary/config.py
"""Config model for summary pipeline."""

from datetime import date, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Any, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.enums import FilingMode
from sec_nlp.pipelines.base import BaseConfig
from sec_nlp.pipelines.settings import LLMSettings, VectorDBSettings


class SummaryConfig(BaseConfig):
    """Configuration for SEC filing summarization pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="SUMMARY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        arbitrary_types_allowed=True,
    )

    # Pipeline metadata
    pipeline_type: str = "summary"

    # Nested configurations with defaults
    llm: LLMSettings = Field(default_factory=LLMSettings)
    vdb: VectorDBSettings = Field(default_factory=VectorDBSettings)

    # User/contact information
    email: str = Field(
        default="your.email@example.com",
        description="Email address for SEC EDGAR requests (required by SEC)",
    )

    # Data paths
    dl_path: Path = Field(
        default=Path("./downloads"),
        description="Path for downloading SEC filings",
    )
    out_path: Path = Field(
        default=Path("./outputs"),
        description="Path for output files",
    )

    # Target configuration
    symbols: list[str] = Field(
        ...,
        description="Stock ticker symbols to process",
        min_length=1,
    )

    # Filing search parameters
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
    keyword: str = Field(
        default="revenue",
        description="Keyword to filter filing chunks",
        min_length=1,
    )

    # Processing parameters
    limit: int | None = Field(
        default=1,
        ge=1,
        description="Maximum number of filings to process per symbol",
    )
    batch_size: int = Field(
        default=16,
        ge=1,
        le=128,
        description="Number of chunks to process in parallel",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed LLM calls",
    )

    # Runtime options
    fresh: bool = Field(
        default=False,
        description="Clear existing output and download folders",
    )
    cleanup: bool = Field(
        default=True,
        description="Clean up downloaded files after processing",
    )

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, v: list[str] | str) -> list[str]:
        """Normalize symbols to uppercase."""
        if isinstance(v, str):
            v = [v]
        return [s.strip().upper() for s in v]

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, v: str) -> str:
        """Validate keyword is non-empty."""
        v = v.strip()
        if not v:
            raise ValueError("keyword must be non-empty")
        return v.lower()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format."""
        import re

        if not re.match(r"[^@]+@[^@]+\.[^@]+", v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_date(cls, v: str | date | None) -> date | None:
        """Parse date string to date object."""
        if v is None or isinstance(v, date):
            return v
        if isinstance(v, str):
            return date.fromisoformat(v)
        raise ValueError(f"Invalid date format: {v}")

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """Validate date range is valid."""
        start, end = self.get_date_range()
        if start > end:
            raise ValueError("start_date cannot be after end_date")
        if start < date(1993, 1, 1):
            raise ValueError(
                "start_date cannot be before 1993-01-01 (SEC EDGAR launch)"
            )
        if end > date.today():
            raise ValueError("end_date cannot be in the future")
        return self

    @model_validator(mode="after")
    def ensure_paths_exist(self) -> Self:
        """Create output and download directories if they don't exist."""
        if self.fresh:
            import shutil

            if self.out_path.exists():
                shutil.rmtree(self.out_path)
            if self.dl_path.exists():
                shutil.rmtree(self.dl_path)

        self.out_path.mkdir(parents=True, exist_ok=True)
        self.dl_path.mkdir(parents=True, exist_ok=True)

        return self

    def get_date_range(self) -> tuple[date, date]:
        """Get computed date range with defaults."""
        today = datetime.today().date()
        one_year_ago = today - timedelta(days=365)
        start = self.start_date or one_year_ago
        end = self.end_date or today
        return start, end

    def get_prompt_path(self) -> Path:
        """Get resolved prompt file path with fallback to default."""
        if self.llm.prompt_file is not None:
            return self.llm.prompt_file

        try:
            prompt_ref = files("sec_nlp") / "prompts" / "summarize.yaml"

            if hasattr(prompt_ref, "__fspath__"):
                return Path(str(prompt_ref))
            else:
                import tempfile

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as tmp:
                    tmp.write(prompt_ref.read_text())
                    return Path(tmp.name)

        except Exception as e:
            raise ValueError(
                f"No prompt file specified and default not found: {e}\n"
                "Please provide a prompt_file in the LLM configuration."
            ) from e

    def to_pipeline_kwargs(self) -> dict[str, Any]:
        """Convert config to pipeline constructor kwargs."""
        start, end = self.get_date_range()
        return {
            "symbols": self.symbols,
            "mode": self.mode,
            "start_date": start,
            "end_date": end,
            "keyword": self.keyword,
            "prompt_file": self.get_prompt_path(),
            "model_name": self.llm.model_name,
            "max_new_tokens": self.llm.max_new_tokens,
            "require_json": self.llm.require_json,
            "limit": self.limit,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "dry_run": self.dry_run,
            "cleanup": self.cleanup,
            "fresh": self.fresh,
            "dl_path": self.dl_path,
            "out_path": self.out_path,
            "email": self.email,
        }
