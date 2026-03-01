# src/sec_nlp/app/flows/compiled.py
"""Compiled flow-stage settings with prevalidated pipeline configs."""

from __future__ import annotations

from dataclasses import dataclass

from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowSpec,
    FlowStageSpec,
)
from sec_nlp.app.flows.registry import (
    CompiledStageSettings,
    resolve_settings_model,
)
from sec_nlp.types import JsonValue

type StageConfigValue = JsonValue


@dataclass(frozen=True, slots=True)
class CompiledStage:
    """Flow stage with prevalidated pipeline settings."""

    stage: FlowStageSpec
    settings: CompiledStageSettings


def compile_stage(
    *,
    stage: FlowStageSpec,
    defaults: FlowDefaults,
) -> CompiledStage:
    """Compile one stage into a prevalidated pipeline settings object."""
    settings_model = resolve_settings_model(stage.pipeline)
    payload: dict[str, StageConfigValue] = {"email": defaults.email}
    payload.update(stage.overrides)
    return CompiledStage(
        stage=stage,
        settings=settings_model.model_validate(payload),
    )


def compile_flow_stages(spec: FlowSpec) -> tuple[CompiledStage, ...]:
    """Compile all stages in a flow spec with prevalidated settings."""
    return tuple(
        compile_stage(stage=stage, defaults=spec.defaults)
        for stage in spec.stages
    )
