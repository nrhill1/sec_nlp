# src/sec_nlp/app/flows/registry.py
"""Registry-based stage dispatch for flow pipeline runnables."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowStageResult,
    FlowStageSpec,
    PipelineName,
)
from sec_nlp.app.flows.runnables import (
    ChatFlowInvokeInput,
    ChatFlowRunnable,
    ExhibitFlowInvokeInput,
    ExhibitFlowRunnable,
    RetrieveFlowInvokeInput,
    RetrieveFlowRunnable,
)

type StageInvokeCallable = Callable[
    [FlowStageSpec, FlowDefaults, FlowArtifactStore], FlowStageResult
]


@dataclass(frozen=True, slots=True)
class FlowStageAdapter:
    """Callable adapter used to execute a concrete flow stage pipeline."""

    pipeline: PipelineName
    invoke: StageInvokeCallable


def _invoke_retrieve_stage(
    stage: FlowStageSpec,
    defaults: FlowDefaults,
    artifacts: FlowArtifactStore,
) -> FlowStageResult:
    return RetrieveFlowRunnable(
        stage=stage,
        defaults=defaults,
        artifacts=artifacts,
    ).invoke(RetrieveFlowInvokeInput())


def _invoke_chat_stage(
    stage: FlowStageSpec,
    defaults: FlowDefaults,
    artifacts: FlowArtifactStore,
) -> FlowStageResult:
    return ChatFlowRunnable(
        stage=stage,
        defaults=defaults,
        artifacts=artifacts,
    ).invoke(ChatFlowInvokeInput())


def _invoke_exhibit_stage(
    stage: FlowStageSpec,
    defaults: FlowDefaults,
    artifacts: FlowArtifactStore,
) -> FlowStageResult:
    return ExhibitFlowRunnable(
        stage=stage,
        defaults=defaults,
        artifacts=artifacts,
    ).invoke(ExhibitFlowInvokeInput())


_FLOW_STAGE_ADAPTERS: dict[str, FlowStageAdapter] = {
    "retrieve": FlowStageAdapter(
        pipeline="retrieve",
        invoke=_invoke_retrieve_stage,
    ),
    "chat": FlowStageAdapter(
        pipeline="chat",
        invoke=_invoke_chat_stage,
    ),
    "exhibit": FlowStageAdapter(
        pipeline="exhibit",
        invoke=_invoke_exhibit_stage,
    ),
}


def resolve_stage_adapter(pipeline: str) -> FlowStageAdapter:
    """Resolve a registered flow stage adapter for the given pipeline name."""
    adapter = _FLOW_STAGE_ADAPTERS.get(pipeline)
    if adapter is None:
        raise ValueError(f"Unsupported flow pipeline '{pipeline}'")
    return adapter
