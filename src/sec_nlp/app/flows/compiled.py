# src/sec_nlp/app/flows/compiled.py
"""Compiled flow-stage settings with prevalidated pipeline configs."""

from __future__ import annotations

from dataclasses import dataclass

from sec_nlp.app.flows.models import FlowDefaults, FlowSpec, FlowStageSpec
from sec_nlp.pipelines.presets.chat import ChatSettings
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings
from sec_nlp.types import JsonValue

type StageConfigValue = JsonValue

type CompiledStageSettings = RetrieveSettings | ChatSettings | ExhibitConfig


@dataclass(frozen=True, slots=True)
class CompiledStage:
    """Flow stage with prevalidated pipeline settings."""

    stage: FlowStageSpec
    settings: CompiledStageSettings


def build_stage_defaults_payload(
    defaults: FlowDefaults,
) -> dict[str, StageConfigValue]:
    """Build stage config payload from flow defaults."""
    return {"email": defaults.email}


def compile_stage(
    *,
    stage: FlowStageSpec,
    defaults: FlowDefaults,
) -> CompiledStage:
    """Compile one stage into a prevalidated pipeline settings object."""
    if stage.pipeline == "retrieve":
        payload: dict[str, StageConfigValue] = build_stage_defaults_payload(
            defaults
        )
        payload.update(stage.overrides)
        return CompiledStage(
            stage=stage,
            settings=RetrieveSettings.model_validate(payload),
        )

    if stage.pipeline == "chat":
        payload = build_stage_defaults_payload(defaults)
        payload.update(stage.overrides)
        return CompiledStage(
            stage=stage,
            settings=ChatSettings.model_validate(payload),
        )

    if stage.pipeline == "exhibit":
        payload = build_stage_defaults_payload(defaults)
        payload.update(stage.overrides)
        return CompiledStage(
            stage=stage,
            settings=ExhibitConfig.model_validate(payload),
        )

    raise ValueError(f"Unsupported flow pipeline '{stage.pipeline}'")


def compile_flow_stages(spec: FlowSpec) -> tuple[CompiledStage, ...]:
    """Compile all stages in a flow spec with prevalidated settings."""
    compiled: list[CompiledStage] = []
    for stage in spec.stages:
        compiled.append(compile_stage(stage=stage, defaults=spec.defaults))
    return tuple(compiled)
