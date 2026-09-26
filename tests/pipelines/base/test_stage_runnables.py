# tests/pipelines/base/test_stage_runnables.py
"""Tests for ordered specialist calls and shared run context."""

from dataclasses import dataclass, field

from pydantic import Field

from sec_nlp.pipelines.base.stages import (
    PipelineStage,
    RunContext,
    StageSequence,
)


@dataclass(slots=True)
class CounterState:
    """Track a sequence's value and applied operations.

    Attributes:
        value: Current counter.
        steps: Applied step names.
    """

    value: int
    steps: list[str] = field(default_factory=list)


class IncrementStage(PipelineStage[CounterState]):
    """Increment typed state and record its operation name."""

    name: str = Field(default="increment")
    delta: int = Field(default=1)

    def _run(self, state: CounterState) -> CounterState:
        """Apply the configured increment."""
        state.value += self.delta
        state.steps.append(self.name)
        return state


def test_sequence_applies_ordered_steps_and_preserves_state() -> None:
    """Execute ordinary calls in order with a shared operation identifier."""
    state = CounterState(value=0)
    context = RunContext(pipeline_type="unit", run_id="run-123")
    sequence = StageSequence(
        (
            IncrementStage(name="first", delta=1),
            IncrementStage(name="second", delta=2),
        ),
        context,
    )
    assert sequence.invoke(state) is state
    assert state.value == 3
    assert state.steps == ["first", "second"]
    assert sequence.context == context
