# src/sec_nlp/app/flows/compiled.py
"""Compile flow specs into typed, prevalidated stage execution plans.

Compilation performs one-time defaults merging and settings validation, then
stores stage-scoped run identifiers so the runner can execute without repeated
model validation or settings-type checks.
"""

from __future__ import annotations

from dataclasses import dataclass

from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowSpec,
    FlowStageSpec,
)
from sec_nlp.app.flows.registry import resolve_settings_model
from sec_nlp.pipelines.presets.analyze import AnalyzeConfig
from sec_nlp.pipelines.presets.chat import ChatSettings
from sec_nlp.pipelines.presets.exb import ExhibitConfig
from sec_nlp.pipelines.presets.retrieve import RetrieveSettings
from sec_nlp.pipelines.presets.warranty import WarrantyConfig
from sec_nlp.types import JsonValue

type StageConfigValue = JsonValue


@dataclass(frozen=True, slots=True)
class CompiledStageBase:
    """Compiled stage metadata shared across all typed flow stages."""

    stage: FlowStageSpec
    pipeline: str
    run_id: str
    run_short_id: int | None


@dataclass(frozen=True, slots=True)
class CompiledRetrieveStage(CompiledStageBase):
    """Compiled retrieve stage with validated retrieve settings."""

    settings: RetrieveSettings


@dataclass(frozen=True, slots=True)
class CompiledChatStage(CompiledStageBase):
    """Compiled chat stage with validated chat settings."""

    settings: ChatSettings


@dataclass(frozen=True, slots=True)
class CompiledExhibitStage(CompiledStageBase):
    """Compiled exhibit stage with validated exhibit settings."""

    settings: ExhibitConfig


@dataclass(frozen=True, slots=True)
class CompiledAnalyzeStage(CompiledStageBase):
    """Compiled analyze stage with validated analyze settings."""

    settings: AnalyzeConfig


@dataclass(frozen=True, slots=True)
class CompiledWarrantyStage(CompiledStageBase):
    """Compiled warranty stage with validated warranty settings."""

    settings: WarrantyConfig


type CompiledStage = (
    CompiledRetrieveStage
    | CompiledChatStage
    | CompiledExhibitStage
    | CompiledAnalyzeStage
    | CompiledWarrantyStage
)


def _run_short_id_or_none(short_id: int) -> int | None:
    """Normalize non-positive short IDs to None for result envelopes."""
    return short_id if short_id > 0 else None


def compile_stage(
    *,
    stage: FlowStageSpec,
    defaults: FlowDefaults,
) -> CompiledStage:
    """Compile one stage into a prevalidated pipeline settings object."""
    settings_model = resolve_settings_model(stage.pipeline)
    payload: dict[str, StageConfigValue] = {"email": defaults.email}
    payload.update(stage.overrides)
    settings = settings_model.model_validate(payload)
    run_short_id = _run_short_id_or_none(settings.short_id)
    match stage.pipeline:
        case "retrieve":
            if not isinstance(settings, RetrieveSettings):
                raise ValueError(
                    "retrieve stage compile produced non-retrieve settings"
                )
            return CompiledRetrieveStage(
                stage=stage,
                pipeline=stage.pipeline,
                run_id=str(settings.run_id),
                run_short_id=run_short_id,
                settings=settings,
            )
        case "chat":
            if not isinstance(settings, ChatSettings):
                raise ValueError(
                    "chat stage compile produced non-chat settings"
                )
            return CompiledChatStage(
                stage=stage,
                pipeline=stage.pipeline,
                run_id=str(settings.run_id),
                run_short_id=run_short_id,
                settings=settings,
            )
        case "exhibit":
            if not isinstance(settings, ExhibitConfig):
                raise ValueError(
                    "exhibit stage compile produced non-exhibit settings"
                )
            return CompiledExhibitStage(
                stage=stage,
                pipeline=stage.pipeline,
                run_id=str(settings.run_id),
                run_short_id=run_short_id,
                settings=settings,
            )
        case "analyze":
            if not isinstance(settings, AnalyzeConfig):
                raise ValueError(
                    "analyze stage compile produced non-analyze settings"
                )
            return CompiledAnalyzeStage(
                stage=stage,
                pipeline=stage.pipeline,
                run_id=str(settings.run_id),
                run_short_id=run_short_id,
                settings=settings,
            )
        case "warranty":
            if not isinstance(settings, WarrantyConfig):
                raise ValueError(
                    "warranty stage compile produced non-warranty settings"
                )
            return CompiledWarrantyStage(
                stage=stage,
                pipeline=stage.pipeline,
                run_id=str(settings.run_id),
                run_short_id=run_short_id,
                settings=settings,
            )
        case _:
            raise ValueError(f"Unsupported flow pipeline '{stage.pipeline}'")


def compile_flow_stages(spec: FlowSpec) -> tuple[CompiledStage, ...]:
    """Compile all stages in a flow spec with prevalidated settings."""
    return tuple(
        compile_stage(stage=stage, defaults=spec.defaults)
        for stage in spec.stages
    )
