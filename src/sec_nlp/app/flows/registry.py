# src/sec_nlp/app/flows/registry.py
"""Registry-based stage dispatch for flow pipeline runnables."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.compiled import CompiledStage
from sec_nlp.app.flows.models import FlowStageResult, PipelineName
from sec_nlp.app.flows.runnables import (
    ChatFlowRunnable,
    ExhibitFlowRunnable,
    RetrieveFlowRunnable,
)
from sec_nlp.pipelines.presets.chat import ChatSettings
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings

type StageInvokeCallable = Callable[
    [CompiledStage, FlowArtifactStore], FlowStageResult
]


@dataclass(frozen=True, slots=True)
class FlowStageAdapter:
    """Callable adapter used to execute a concrete flow stage pipeline."""

    pipeline: PipelineName
    invoke: StageInvokeCallable


def _invoke_retrieve_stage(
    stage: CompiledStage,
    artifacts: FlowArtifactStore,
) -> FlowStageResult:
    if not isinstance(stage.settings, RetrieveSettings):
        raise ValueError("retrieve stage received non-retrieve settings")

    return RetrieveFlowRunnable(
        stage=stage.stage,
        artifacts=artifacts,
        compiled_config=stage.settings,
    ).invoke()


def _invoke_chat_stage(
    stage: CompiledStage,
    artifacts: FlowArtifactStore,
) -> FlowStageResult:
    if not isinstance(stage.settings, ChatSettings):
        raise ValueError("chat stage received non-chat settings")

    return ChatFlowRunnable(
        stage=stage.stage,
        artifacts=artifacts,
        compiled_config=stage.settings,
    ).invoke()


def _invoke_exhibit_stage(
    stage: CompiledStage,
    artifacts: FlowArtifactStore,
) -> FlowStageResult:
    if not isinstance(stage.settings, ExhibitConfig):
        raise ValueError("exhibit stage received non-exhibit settings")

    return ExhibitFlowRunnable(
        stage=stage.stage,
        artifacts=artifacts,
        compiled_config=stage.settings,
    ).invoke()


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
