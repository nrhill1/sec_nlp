# src/sec_nlp/app/flows/compiled.py
"""Compiled flow-stage settings with prevalidated pipeline configs."""

from __future__ import annotations

from dataclasses import dataclass

from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowSpec,
    FlowStageSpec,
    PipelineName,
)
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
type StageSettingsModel = (
    type[RetrieveSettings]
    | type[ChatSettings]
    | type[ExhibitConfig]
    | type[AnalyzeConfig]
    | type[WarrantyConfig]
)

PIPELINE_TO_SETTINGS_MODEL: dict[PipelineName, StageSettingsModel] = {
    "retrieve": RetrieveSettings,
    "chat": ChatSettings,
    "exhibit": ExhibitConfig,
    "analyze": AnalyzeConfig,
    "warranty": WarrantyConfig,
}


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
    settings_model = PIPELINE_TO_SETTINGS_MODEL.get(stage.pipeline)
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
    return tuple(
        compile_stage(stage=stage, defaults=spec.defaults)
        for stage in spec.stages
    )
