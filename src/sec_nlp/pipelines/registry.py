# sec_nlp/pipelines/registry.py
"""Pipeline type registration and discovery with Pydantic validation."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from sec_nlp.core import get_logger
from sec_nlp.pipelines.base import BaseConfig, BasePipeline, C, R

logger = get_logger(__name__)


class PipelineInfo(BaseModel):
    """Information about a registered pipeline type."""

    type_id: str = Field(..., description="Pipeline type identifier")
    class_name: str = Field(..., description="Python class name")
    description: str = Field(..., description="Human-readable description")
    requires_llm: bool = Field(default=False, description="Requires LLM model")
    requires_vector_db: bool = Field(default=False, description="Requires vector database")
    module: str = Field(..., description="Module path")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate pipeline type is lowercase alphanumeric with hyphens."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Pipeline type must be alphanumeric with hyphens/underscores")
        return v.lower()


class PipelineRegistry(BaseModel):
    """
    Registry for pipeline types with validation.

    This is a singleton-style registry that maintains a mapping of
    pipeline type identifiers to their implementations.
    """

    _pipelines: ClassVar[dict[str, type[BasePipeline[Any]]]] = {}
    _info: ClassVar[dict[str, PipelineInfo]] = {}

    @classmethod
    def register(cls, pipeline_type: str) -> Any:
        """
        Decorator to register a pipeline type with validation.

        Usage:
            @PipelineRegistry.register("summary")
            class SummaryPipeline(BasePipeline[SummaryConfig]):
                description = "Summarize SEC filings"
                requires_model = True
                ...
        """

        def decorator(pipeline_class: type[BasePipeline[C, R]]) -> type[BasePipeline[C, R]]:
            # Validate and create pipeline info
            try:
                info = PipelineInfo(
                    type=pipeline_type,
                    class_name=pipeline_class.__name__,
                    description=getattr(pipeline_class, "description", "No description provided"),
                    requires_model=getattr(pipeline_class, "requires_model", False),
                    requires_vector_db=getattr(pipeline_class, "requires_vector_db", False),
                    config_class_name=pipeline_class.get_config_class().__name__,
                    module=pipeline_class.__module__,
                )
            except Exception as e:
                raise ValueError(
                    f"Failed to create PipelineInfo for {pipeline_class.__name__}: {e}"
                ) from e

            if pipeline_type in cls._pipelines:
                logger.warning(
                    "Pipeline type '%s' already registered, overwriting %s with %s",
                    pipeline_type,
                    cls._pipelines[pipeline_type].__name__,
                    pipeline_class.__name__,
                )

            cls._pipelines[pipeline_type] = pipeline_class
            cls._info[pipeline_type] = info
            pipeline_class.pipeline_type = pipeline_type

            logger.debug(
                "Registered pipeline: %s -> %s",
                pipeline_type,
                pipeline_class.__name__,
            )

            return pipeline_class

        return decorator

    @classmethod
    def get(cls, pipeline_type: str) -> type[BasePipeline[C, R]]:
        """Get a pipeline class by type."""
        if pipeline_type not in cls._pipelines:
            available = ", ".join(cls._pipelines.keys())
            raise ValueError(
                f"Unknown pipeline type: '{pipeline_type}'. "
                f"Available: {available or '(none registered)'}"
            )
        return cls._pipelines[pipeline_type]

    @classmethod
    def get_info(cls, pipeline_type: str) -> PipelineInfo:
        """Get validated information about a pipeline type."""
        if pipeline_type not in cls._info:
            raise ValueError(f"Unknown pipeline type: '{pipeline_type}'")
        return cls._info[pipeline_type]

    @classmethod
    def get_all(cls) -> dict[str, type[BasePipeline[C, R]]]:
        """Get all registered pipelines."""
        return cls._pipelines.copy()

    @classmethod
    def get_all_info(cls) -> dict[str, PipelineInfo]:
        """Get information about all registered pipelines."""
        return cls._info.copy()

    @classmethod
    def list_types(cls) -> list[str]:
        """List all registered pipeline types."""
        return sorted(cls._pipelines.keys())

    @classmethod
    def to_dict(cls) -> dict[str, Any]:
        """Export registry state as dictionary."""
        return {
            "pipelines": {ptype: info.model_dump() for ptype, info in cls._info.items()},
            "count": len(cls._pipelines),
        }

    @classmethod
    def validate_requirements(cls, pipeline_type: str) -> dict[str, bool]:
        """
        Check if requirements for a pipeline are met.

        Returns:
            Dict with requirement checks and status
        """
        info = cls.get_info(pipeline_type)

        checks = {
            "pipeline_registered": True,
            "model_available": True,  # TODO: Check actual model availability
            "vector_db_available": True,  # TODO: Check actual Qdrant connection
        }

        if info.requires_model:
            # TODO: Add actual check for model availability
            checks["model_required"] = True

        if info.requires_vector_db:
            # TODO: Add actual check for vector DB connection
            checks["vector_db_required"] = True

        return checks

    @classmethod
    def get_config_class(cls, pipeline_type: str) -> type[BaseConfig]:
        return cls._pipelines[pipeline_type].get_config_class()
