# src/sec_nlp/pipelines/base/stages.py
"""Frozen, serializable stage primitives for pipeline state transitions.

Each pipeline step (search, embed, index, analyze, etc.) is a
``PipelineStageRunnable`` that receives a mutable state object, performs one
transformation, and returns the same state. Stages are composed into chains
via ``BasePipeline.build_configured_stage_chain``, which attaches
LangChain tracing metadata (pipeline type, run ID, deterministic UUID).
"""

from __future__ import annotations

from abc import abstractmethod
from uuid import NAMESPACE_URL, uuid5

from langchain_core.runnables import (
    Runnable,
    RunnableConfig,
    RunnableSerializable,
)
from pydantic import ConfigDict, Field

from sec_nlp.types import ConfigValue


class PipelineStageRunnable[StageStateT](
    RunnableSerializable[StageStateT, StageStateT]
):
    """Frozen ``RunnableSerializable`` base for a single pipeline stage.

    Subclasses implement ``_run(state)`` to mutate and return the shared
    pipeline state. The ``configured()`` method attaches stable LangChain
    metadata for tracing and observability.
    """

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
        """Apply this stage's transformation to the pipeline state and return it."""
        _ = config
        _ = kwargs
        return self._run(input)

    def configured(
        self,
        *,
        pipeline_type: str,
        run_id: str | None = None,
    ) -> Runnable[StageStateT, StageStateT]:
        """Return a copy of this runnable with LangChain tracing tags and metadata."""
        metadata: dict[str, str] = {
            "pipeline_type": pipeline_type,
            "stage_name": self.name,
        }
        if run_id is not None:
            metadata["run_id"] = run_id
            metadata["stage_debug_uuid"] = str(
                uuid5(
                    NAMESPACE_URL,
                    f"{run_id}:{pipeline_type}:{self.name}",
                )
            )
        return self.with_config(
            run_name=self.name,
            tags=[f"pipeline:{pipeline_type}", f"stage:{self.name}"],
            metadata=metadata,
        )

    @abstractmethod
    def _run(self, state: StageStateT) -> StageStateT:
        """Mutate and return the provided state instance."""
