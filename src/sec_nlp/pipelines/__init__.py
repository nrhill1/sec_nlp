# src/sec_nlp/pipelines/__init__.py
"""Pipeline implementations."""

from .analysis import AnalysisPipeline
from .base import BaseConfig, BasePipeline, BaseResult, PipelineModel
from .embed import EmbeddingPipeline
from .registry import PipelineRegistry
from .settings import LLMSettings, VectorDBSettings
from .summary import SummaryPipeline

__all__: list[str] = [
    # Base
    "BaseConfig",
    "BasePipeline",
    "BaseResult",
    "PipelineModel"
    # Pipelines
    "SummaryPipeline",
    "AnalysisPipeline",
    "EmbeddingPipeline",
    # Registry
    "PipelineRegistry",
    "PipelineInfo",
    # Settings
    "LLMSettings",
    "VectorDBSettings",
]
