# src/sec_nlp/pipelines/base/__init__.py
"""Base pipeline interfaces and validation utilities."""

from sec_nlp.core.infra.logger import logger

from .config import BasePipelineSettings
from .pipeline import BasePipeline
from .result import BasePipelineResult
from .stages import PipelineStageRunnable
from .validation import (
    PipelineValidator,
    ValidationReport,
    ValidationResult,
    validate_pipeline,
)

__all__: tuple[str, ...] = (
    "BasePipeline",
    "BasePipelineSettings",
    "BasePipelineResult",
    "PipelineStageRunnable",
    "PipelineValidator",
    "ValidationReport",
    "ValidationResult",
    "validate_pipeline",
    "logger",
)
