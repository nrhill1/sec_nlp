# src/sec_nlp/pipelines/base/validation.py
"""Pre-flight validation utilities for pipelines."""

import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import color_text, logger
from sec_nlp.pipelines.exceptions import (
    InvalidDateException,
    InvalidEmailException,
    InvalidLLMException,
    InvalidPathException,
    InvalidSymbolException,
    LLMUnavailableException,
    MissingDependencyException,
    VectorUnavailableException,
)
from sec_nlp.pipelines.utils import is_valid_email
from sec_nlp.types import JsonValue

from .config import BaseConfig


class ValidationResult(BaseModel):
    """Result of a validation check."""

    model_config = ConfigDict(
        frozen=True,
        defer_build=True,
    )

    passed: bool = Field(description="Whether validation passed")
    check_name: str = Field(description="Name of the validation check")
    message: str = Field(description="Validation message or error details")
    severity: str = Field(
        default="error",
        description="Severity level: 'error', 'warning', 'info'",
    )
    details: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Additional validation details",
    )


class ValidationReport(BaseModel):
    """Aggregated validation report."""

    model_config = ConfigDict(
        frozen=False,
        defer_build=True,
    )

    all_passed: bool = Field(
        default=True, description="Whether all critical checks passed"
    )
    checks: list[ValidationResult] = Field(
        default_factory=list, description="Individual validation results"
    )
    errors: int = Field(default=0, description="Number of error-level issues")
    warnings: int = Field(default=0, description="Number of warnings")

    def add_check(self, result: ValidationResult) -> None:
        """Add a check result and update counters/overall status."""
        self.checks.append(result)
        if result.severity == "error":
            self.errors += 1
        elif result.severity == "warning":
            self.warnings += 1
        self.all_passed = self.errors == 0

    def has_errors(self) -> bool:
        """Return True if any error-level checks exist."""
        return self.errors > 0

    def print_report(self) -> None:
        """Log a human-readable report summary."""
        status_text = "PASSED" if self.all_passed else "FAILED"
        status_color = "green" if self.all_passed else "red"
        logger.info(
            color_text(f"Validation Report - {status_text}", color=status_color)
        )

        for chk in self.checks:
            icon = {"error": "✗", "warning": "⚠", "info": "✓"}.get(
                chk.severity, "•"
            )
            msg = f"{icon} {chk.check_name}: {chk.message}"
            if chk.severity == "error":
                logger.error(msg)
            elif chk.severity == "warning":
                logger.warning(msg)
            else:
                logger.info(color_text(msg, color="blue"))


class PipelineValidator(BaseModel):
    """Validates pipeline requirements before execution."""

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        defer_build=True,
    )

    config: BaseConfig = Field(description="Pipeline configuration to validate")
    report: ValidationReport = Field(
        default_factory=ValidationReport,
        description="Validation report accumulator",
    )

    def validate_all(self) -> ValidationReport:
        """Run all validation checks and return a report."""
        self.report = ValidationReport()

        self._check_email()
        self._check_paths()
        self._check_disk_space()
        self._check_symbols()
        self._check_date_range()

        llm_config = getattr(self.config, "llm", None)
        if llm_config is not None:
            self._check_llm()

        vdb_config = getattr(self.config, "vdb", None)
        if vdb_config is not None:
            self._check_vector_db()

        self.report.all_passed = not self.report.has_errors()
        return self.report

    def _check_email(self) -> None:
        """Validate email configuration.

        Raises:
            InvalidEmailException: If email is invalid or missing
        """
        email = self.config.email

        if (
            not email
            or not is_valid_email(email)
            or email == "your.email@example.com"
        ):
            error_msg = (
                "Invalid or missing email. SEC requires a valid contact email."
            )
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="Email Configuration",
                    message=error_msg,
                    severity="error",
                    details={"current_value": email or "None"},
                )
            )
            raise InvalidEmailException(error_msg)

        self.report.add_check(
            ValidationResult(
                passed=True,
                check_name="Email Configuration",
                message=f"Valid email configured: {email}",
                severity="info",
            )
        )

    def _validate_path(self, path: str | Path, check_name: str) -> None:
        """Validate that a path is writable.

        Args:
            path: Path to validate (string or Path object)
            check_name: Name of the check for reporting

        Raises:
            InvalidPathException: If path is not writable or cannot be created
        """
        try:
            path_obj = Path(path) if isinstance(path, str) else path
            path_obj.mkdir(parents=True, exist_ok=True)

            test_file = path_obj / ".write_test"
            test_file.touch()
            test_file.unlink()

            self.report.add_check(
                ValidationResult(
                    passed=True,
                    check_name=check_name,
                    message=f"{check_name} is writable: {path_obj}",
                    severity="info",
                    details={"path": str(path_obj.resolve())},
                )
            )
        except (OSError, PermissionError, TypeError) as e:
            error_msg = f"{check_name} not writable: {e}"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name=check_name,
                    message=error_msg,
                    severity="error",
                    details={"path": str(path)},
                )
            )
            raise InvalidPathException(error_msg) from e

    def _check_paths(self) -> None:
        """Validate output and download paths.

        Raises:
            InvalidPathException: If paths are not writable
        """
        self._validate_path(self.config.out_path, "Output Path")
        self._validate_path(self.config.dl_path, "Downloads Path")

    def _check_disk_space(self) -> None:
        """Check that there is enough disk space for downloads."""
        try:
            usage = shutil.disk_usage(self.config.dl_path)
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)

            if free_gb < 1.0:
                msg = f"Low disk space: {free_gb:.2f} GB free of {total_gb:.2f} GB"
                self.report.add_check(
                    ValidationResult(
                        passed=False,
                        check_name="Disk Space",
                        message=msg,
                        severity="warning",
                        details={"free_gb": free_gb, "total_gb": total_gb},
                    )
                )
            else:
                msg = f"Sufficient disk space: {free_gb:.2f} GB free of {total_gb:.2f} GB"
                self.report.add_check(
                    ValidationResult(
                        passed=True,
                        check_name="Disk Space",
                        message=msg,
                        severity="info",
                        details={"free_gb": free_gb, "total_gb": total_gb},
                    )
                )
        except Exception as e:  # pragma: no cover - system dependent
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="Disk Space",
                    message=f"Could not check disk space: {e}",
                    severity="warning",
                )
            )

    def _check_symbols(self) -> None:
        """Validate symbol list.

        Raises:
            InvalidSymbolException: If symbol list is empty or invalid
        """
        if not self.config.symbols:
            msg = "No symbols provided"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="Symbols",
                    message=msg,
                    severity="error",
                )
            )
            raise InvalidSymbolException(msg)

        invalid = [s for s in self.config.symbols if not s.isalnum()]
        if invalid:
            msg = f"Invalid symbols: {', '.join(invalid)}"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="Symbols",
                    message=msg,
                    severity="error",
                    details={"invalid_symbols": invalid},
                )
            )
            raise InvalidSymbolException(msg)

        self.report.add_check(
            ValidationResult(
                passed=True,
                check_name="Symbols",
                message=f"{len(self.config.symbols)} symbols configured",
                severity="info",
                details={"symbols": self.config.symbols},
            )
        )

    def _check_date_range(self) -> None:
        """Validate date range configuration.

        Raises:
            InvalidDateException: If date range is invalid
        """
        try:
            start, end = self.config.date_range
            msg = f"Date range: {start} to {end}"
            self.report.add_check(
                ValidationResult(
                    passed=True,
                    check_name="Date Range",
                    message=msg,
                    severity="info",
                    details={"start": str(start), "end": str(end)},
                )
            )
        except ValueError as e:
            msg = f"Invalid date range: {e}"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="Date Range",
                    message=msg,
                    severity="error",
                )
            )
            raise InvalidDateException(msg) from e

    def _check_llm(self) -> None:
        """Validate LLM configuration and connectivity.

        Raises:
            InvalidLLMException: If LLM configuration is invalid
            MissingDependencyException: If requests is not installed
            LLMUnavailableException: If the LLM endpoint is unreachable
        """
        from sec_nlp.pipelines.llm import LLMConfig

        llm_config = getattr(self.config, "llm", None)
        assert isinstance(llm_config, LLMConfig), "llm must be LLMConfig"

        if not llm_config.base_url:
            error_msg = "LLM base URL not configured"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="LLM Configuration",
                    message=error_msg,
                    severity="error",
                )
            )
            raise InvalidLLMException(error_msg)

        try:
            import requests
            from requests.exceptions import (
                ConnectionError,
                RequestException,
                Timeout,
            )
        except ImportError as e:
            error_msg = "requests is not installed"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="LLM Configuration",
                    message=error_msg,
                    severity="error",
                )
            )
            raise MissingDependencyException(error_msg) from e

        try:
            response = requests.get(
                llm_config.base_url, timeout=llm_config.timeout
            )
            if response.status_code >= 400:
                error_msg = (
                    f"LLM endpoint returned status code {response.status_code}"
                )
                self.report.add_check(
                    ValidationResult(
                        passed=False,
                        check_name="LLM Availability",
                        message=error_msg,
                        severity="warning",
                    )
                )
                raise LLMUnavailableException(error_msg)

            self.report.add_check(
                ValidationResult(
                    passed=True,
                    check_name="LLM Availability",
                    message="LLM endpoint reachable",
                    severity="info",
                )
            )
        except (ConnectionError, Timeout) as e:
            error_msg = f"Cannot connect to Ollama: {e}"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="LLM Availability",
                    message=error_msg,
                    severity="warning",
                )
            )
            raise LLMUnavailableException(error_msg) from e
        except RequestException as e:
            error_msg = f"LLM check failed: {e}"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="LLM Availability",
                    message=error_msg,
                    severity="warning",
                )
            )
            raise LLMUnavailableException(error_msg) from e

    def _check_vector_db(self) -> None:
        """Validate vector database configuration and connectivity.

        Raises:
            VectorUnavailableException: If Qdrant service is unavailable
            MissingDependencyException: If qdrant-client is not installed
        """
        from sec_nlp.pipelines.vector import VectorConfig

        vdb_config = getattr(self.config, "vdb", None)
        assert isinstance(vdb_config, VectorConfig), "vdb must be VectorConfig"

        try:
            from qdrant_client import QdrantClient
        except ImportError as e:
            error_msg = "qdrant-client not installed"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="Vector Database",
                    message=error_msg,
                    severity="error",
                )
            )
            raise MissingDependencyException(error_msg) from e

        try:
            qdrant_location = vdb_config.qdrant_location
            qdrant_url = vdb_config.qdrant_url
            qdrant_host = vdb_config.qdrant_host
            qdrant_port = vdb_config.qdrant_port
            api_key = vdb_config.qdrant_api_key

            if qdrant_location:
                client = QdrantClient(location=qdrant_location, timeout=5)
                target = qdrant_location
                target_label = "location"
                target_message = "embedded Qdrant"
            else:
                target = (
                    qdrant_url
                    if qdrant_url
                    else f"http://{qdrant_host}:{qdrant_port}"
                )
                client = QdrantClient(url=target, api_key=api_key, timeout=5)
                target_label = "url"
                target_message = "Qdrant"

            collections = client.get_collections()

            self.report.add_check(
                ValidationResult(
                    passed=True,
                    check_name="Vector Database",
                    message=f"Connected to {target_message} at {target}",
                    severity="info",
                    details={
                        target_label: target,
                        "collections": len(collections.collections),
                    },
                )
            )

        except Exception as e:
            error_msg = f"Cannot connect to Qdrant: {e}"
            self.report.add_check(
                ValidationResult(
                    passed=False,
                    check_name="Vector Database",
                    message=error_msg,
                    severity="error",
                    details={"target": "unknown"},
                )
            )
            raise VectorUnavailableException(error_msg) from e


def validate_pipeline(
    config: BaseConfig, print_report: bool = True
) -> ValidationReport:
    """Convenience entrypoint to validate a pipeline config.

    Args:
        config: Pipeline configuration to validate
        print_report: Whether to print validation report to logger

    Returns:
        ValidationReport containing all validation results
    """
    validator = PipelineValidator(config=config)
    report = validator.validate_all()
    if print_report:
        report.print_report()
    return report
