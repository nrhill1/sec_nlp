# src/sec_nlp/pipelines/base/stages.py
"""Shared runnable stage primitives for pipeline state transitions."""

from __future__ import annotations

from abc import abstractmethod
from typing import TypeVar

from langchain_core.runnables import (
    Runnable,
    RunnableConfig,
    RunnableSerializable,
)
from pydantic import ConfigDict, Field

from sec_nlp.types import ConfigValue

StageStateT = TypeVar("StageStateT")


class PipelineStageRunnable[StageStateT](
    RunnableSerializable[StageStateT, StageStateT]
):
    """Base class for stage-level runnable state transitions."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    name: str = Field(min_length=1)

    def invoke(
        self,
        input: StageStateT,
        config: RunnableConfig | None = None,
        **kwargs: ConfigValue,
    ) -> StageStateT:
        """Invoke one stage against the mutable pipeline state."""
        _ = config
        _ = kwargs
        return self._run(input)

    def configured(
        self, *, pipeline_type: str
    ) -> Runnable[StageStateT, StageStateT]:
        """Return a stage runnable configured with stable tracing metadata."""
        return self.with_config(
            run_name=self.name,
            tags=[f"pipeline:{pipeline_type}", f"stage:{self.name}"],
        )

    @abstractmethod
    def _run(self, state: StageStateT) -> StageStateT:
        """Mutate and return the provided state instance."""
