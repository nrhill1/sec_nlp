# src/sec_nlp/app/flows/compiled.py
"""Compiled flow-stage settings with prevalidated pipeline configs."""

from __future__ import annotations

from dataclasses import dataclass

from sec_nlp.app.flows.models import FlowDefaults, FlowSpec, FlowStageSpec
from sec_nlp.pipelines.presets.analyze import AnalyzeConfig
from sec_nlp.pipelines.presets.chat import ChatSettings
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings
from sec_nlp.pipelines.presets.warranty import WarrantyConfig
from sec_nlp.types import JsonValue

type StageConfigValue = JsonValue

type CompiledStageSettings = (
    RetrieveSettings
    | ChatSettings
    | ExhibitConfig
    | AnalyzeConfig
    | WarrantyConfig
)


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
    pipeline_to_model = {
        "retrieve": RetrieveSettings,
        "chat": ChatSettings,
        "exhibit": ExhibitConfig,
        "analyze": AnalyzeConfig,
        "warranty": WarrantyConfig,
    }
    settings_model = pipeline_to_model.get(stage.pipeline)
    if settings_model is None:
        raise ValueError(f"Unsupported flow pipeline '{stage.pipeline}'")

    payload: dict[str, StageConfigValue] = {"email": defaults.email}
    payload.update(stage.overrides)
    return CompiledStage(
        stage=stage,
        settings=settings_model.model_validate(payload),
    )


def compile_flow_stages(spec: FlowSpec) -> tuple[CompiledStage, ...]:
    """Compile all stages in a flow spec with prevalidated settings."""
    compiled: list[CompiledStage] = []
    for stage in spec.stages:
        compiled.append(compile_stage(stage=stage, defaults=spec.defaults))
    return tuple(compiled)
