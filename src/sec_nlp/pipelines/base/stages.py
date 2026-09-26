# src/sec_nlp/pipelines/base/stages.py
"""Sequential specialist operations with lightweight run context.

The services retain their typed state and extraction steps. Execution is a
normal Python loop with shared run identifiers, without graph compilation or
an AI runtime dependency.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import logger


@dataclass(frozen=True, slots=True)
class RunContext:
    """Identify one user-triggered specialist operation for diagnostic logging.

    Attributes:
        pipeline_type: Specialist service name.
        run_id: Identifier shared by exported artifacts.
    """

    pipeline_type: str
    run_id: str


class PipelineStage[StageStateT](BaseModel, ABC):
    """Apply one deterministic transformation to a specialist's typed state.

    Subclasses keep their existing parsing and export logic. The caller owns
    orchestration, cancellation, and display; stages never construct a graph.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True, extra="forbid", frozen=True
    )
    name: str = Field(
        min_length=1, description="Diagnostic name for this step."
    )

    def invoke(self, state: StageStateT) -> StageStateT:
        """Apply this step and return its updated typed state."""
        return self._run(state)

    @abstractmethod
    def _run(self, state: StageStateT) -> StageStateT:
        """Apply the specialized extraction or export operation."""


@dataclass(frozen=True, slots=True)
class StageSequence[StageStateT]:
    """Execute an ordered tuple of specialist steps through ordinary calls.

    Attributes:
        stages: Operations in their required execution order.
        context: Run identifiers for diagnostics.
    """

    stages: tuple[PipelineStage[StageStateT], ...]
    context: RunContext

    def invoke(self, state: StageStateT) -> StageStateT:
        """Run each operation and return the final state."""
        for stage in self.stages:
            logger.debug(
                "%s/%s: %s",
                self.context.pipeline_type,
                self.context.run_id,
                stage.name,
            )
            state = stage.invoke(state)
        return state
