# src/sec_nlp/pipelines/composition/__init__.py
"""Pipeline composition framework for chaining pipelines."""

from .chain import ChainResult, PipelineChain, StageResult
from .stage import (
    PipelineStage,
    StageOutput,
    create_stage,
    has_metadata_key,
    has_outputs,
    is_successful,
)

__all__ = [
    "ChainResult",
    "PipelineChain",
    "PipelineStage",
    "StageOutput",
    "StageResult",
    "create_stage",
    "has_metadata_key",
    "has_outputs",
    "is_successful",
]
