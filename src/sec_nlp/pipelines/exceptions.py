"""Exception hierarchy for pipeline validation and execution.

This module defines a comprehensive exception hierarchy following Python
conventions and industry best practices. Exceptions are organized by:
1. Base class: PipelineException
2. Category: Validation, Configuration, Runtime, External Service
3. Specificity: Detailed error types for each category
"""


# ============================================================================
# Base Exception
# ============================================================================


class PipelineException(Exception):
    """Base exception for all pipeline operations.

    All pipeline-related exceptions inherit from this class, allowing
    consumers to catch all pipeline errors with a single except clause.
    """

    pass


# ============================================================================
# Validation Exceptions
# ============================================================================


class InvalidEmailException(PipelineException):
    """Email address is invalid or missing."""

    pass


class InvalidSymbolException(PipelineException):
    """Ticker symbol is invalid or malformed."""

    pass


class InvalidDateException(PipelineException):
    """Date range is invalid (start >= end)."""

    pass


# ============================================================================
# Configuration Exceptions
# ============================================================================


class InvalidPathException(PipelineException):
    """Path is invalid, inaccessible, or not writable."""

    pass


class InvalidLLMException(PipelineException):
    """LLM configuration is invalid or incomplete."""

    pass


class InvalidVectorException(PipelineException):
    """Vector store configuration is invalid or inaccessible."""

    pass


# ============================================================================
# Runtime Exceptions
# ============================================================================


class InsufficientDiskException(PipelineException):
    """Insufficient disk space to complete operation."""

    pass


class LLMUnavailableException(PipelineException):
    """LLM service (Ollama) is unavailable or unresponsive."""

    pass


class VectorUnavailableException(PipelineException):
    """Vector store service (Qdrant) is unavailable or unresponsive."""

    pass


# ============================================================================
# Dependency Exceptions
# ============================================================================


class MissingDependencyException(PipelineException):
    """Required library or package is not installed."""

    pass


class IncompatibleDependencyException(PipelineException):
    """Installed library version is incompatible or broken."""

    pass


# ============================================================================
# Module Exports
# ============================================================================

__all__: tuple[str, ...] = (
    # Base
    "PipelineException",
    # Validation
    "InvalidEmailException",
    "InvalidSymbolException",
    "InvalidDateException",
    # Configuration
    "InvalidPathException",
    "InvalidLLMException",
    "InvalidVectorException",
    # Runtime
    "InsufficientDiskException",
    "LLMUnavailableException",
    "VectorUnavailableException",
    # Dependencies
    "MissingDependencyException",
    "IncompatibleDependencyException",
)
