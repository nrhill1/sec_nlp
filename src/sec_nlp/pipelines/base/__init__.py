# src/sec_nlp/pipelines/base/__init__.py
"""Base pipeline interfaces and validation utilities."""

from sec_nlp.core.infra.logger import logger

from .config import BaseConfig
from .pipeline import BasePipeline
from .result import BaseResult
from .validation import (
    PipelineValidator,
    ValidationReport,
    ValidationResult,
    validate_pipeline,
)

__all__: tuple[str, ...] = (
    "BasePipeline",
    "BaseConfig",
    "BaseResult",
    "PipelineValidator",
    "ValidationReport",
    "ValidationResult",
    "validate_pipeline",
    "logger",
)
