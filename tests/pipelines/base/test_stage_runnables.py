# tests/pipelines/base/test_stage_runnables.py
"""Tests for shared runnable stage primitives."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from sec_nlp.pipelines.base.stages import PipelineStageRunnable


@dataclass(slots=True)
class CounterState:
    """Mutable state used to verify in-place stage mutation semantics."""

    value: int
    steps: list[str] = field(default_factory=list)


class IncrementStage(PipelineStageRunnable[CounterState]):
    """Simple stage that increments a counter and records its name."""

    name: str = Field(default="increment")
    delta: int = Field(default=1)

    def _run(self, state: CounterState) -> CounterState:
        state.value += self.delta
        state.steps.append(self.name)
        return state


def test_stage_chain_invokes_in_order_and_preserves_identity() -> None:
    state = CounterState(value=0)
    chain = IncrementStage(name="first", delta=1) | IncrementStage(
        name="second",
        delta=2,
    )

    initial_state_id = id(state)
    final_state = chain.invoke(state)

    assert id(final_state) == initial_state_id
    assert final_state.value == 3
    assert final_state.steps == ["first", "second"]


def test_configured_stage_preserves_identity() -> None:
    state = CounterState(value=5)
    configured = IncrementStage(name="configured", delta=4).configured(
        pipeline_type="unit",
    )

    initial_state_id = id(state)
    final_state = configured.invoke(state)

    assert id(final_state) == initial_state_id
    assert final_state.value == 9
    assert final_state.steps == ["configured"]
