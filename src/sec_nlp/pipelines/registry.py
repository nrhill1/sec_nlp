# src/sec_nlp/pipelines/registry.py
"""Pipeline type registration and discovery with Pydantic validation."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from sec_nlp.core import get_logger
from sec_nlp.pipelines.base import (
    BaseConfig,
    PipelineModel,
)

logger = get_logger(__name__)


class PipelineRegistry(BaseModel):
    """
    Registry for pipeline types with validation.

    This is a singleton-style registry that maintains a mapping of
    pipeline type identifiers to their implementations.
    """

    _pipelines: ClassVar[dict[str, PipelineModel]] = {}

    @classmethod
    def register(cls, pipeline_type: str) -> Any:
        """
        Decorator to register a pipeline type with validation.

        Usage:
            @PipelineRegistry.register("summary")
            class SummaryPipeline(BasePipeline[BaseConfig, BaseModel, BaseResult][SummaryConfig]):
                description = "Summarize SEC filings"
                requires_model = True
                ...
        """

        def decorator(
            pipeline_class: PipelineModel,
        ) -> PipelineModel:
            if pipeline_type in cls._pipelines:
                logger.warning(
                    "Pipeline type '%s' already registered, overwriting %s with %s",
                    pipeline_type,
                    cls._pipelines[pipeline_type].__name__,
                    pipeline_class.__name__,
                )

            cls._pipelines[pipeline_type] = pipeline_class
            pipeline_class.pipeline_type = pipeline_type

            logger.debug(
                "Registered pipeline: %s -> %s",
                pipeline_type,
                pipeline_class.__name__,
            )

            return pipeline_class

        return decorator

    @classmethod
    def get_pipeline(cls, pipeline_type: str) -> PipelineModel:
        """Get a pipeline class by type."""
        if pipeline_type not in cls._pipelines:
            available = ", ".join(cls._pipelines.keys())
            raise ValueError(
                f"Unknown pipeline type: '{pipeline_type}'. "
                f"Available: {available or '(none registered)'}"
            )
        return cls._pipelines[pipeline_type]

    @classmethod
    def get_all_pipelines(
        cls,
    ) -> list[PipelineModel]:
        return list(cls._pipelines.values())

    @classmethod
    def list_types(cls) -> list[str]:
        """List all registered pipeline types."""
        return sorted(cls._pipelines.keys())

    @classmethod
    def get_pipeline_config_class(cls, pipeline_type: str) -> type[BaseConfig]:
        pipeline = cls._pipelines.get(pipeline_type)
        if pipeline is None:
            raise ValueError(f"Unknown pipeline type: '{pipeline_type}'")
        return pipeline._config_class
