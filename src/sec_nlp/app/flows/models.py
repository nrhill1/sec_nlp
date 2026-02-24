# src/sec_nlp/app/flows/models.py
"""Models for multi-pipeline flow orchestration."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from sec_nlp.types import JsonValue


class FlowDefaults(BaseModel):
    """Shared defaults merged into each stage configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email: str = Field(
        description="SEC contact email used by downstream pipelines."
    )
    symbols: list[str] = Field(
        default_factory=list,
        description="Default ticker scope for flow stages.",
    )
    forms: list[str] | None = Field(
        default=None,
        description="Optional default form filters applied to stages.",
    )
    start_date: date | None = Field(
        default=None,
        description="Optional start date shared by stages.",
    )
    end_date: date | None = Field(
        default=None,
        description="Optional end date shared by stages.",
    )
    dl_path: Path | None = Field(
        default=None,
        description="Optional shared downloads path.",
    )
    out_path: Path | None = Field(
        default=None,
        description="Optional shared outputs path.",
    )
    dry_run: bool | None = Field(
        default=None,
        description="Optional shared dry-run default for stages.",
    )

    @field_validator("symbols", mode="before")
    @classmethod
    def _normalize_symbols(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            symbol = raw.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized.append(symbol)
        return normalized

    @model_validator(mode="after")
    def _validate_dates(self) -> FlowDefaults:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError(
                "defaults.start_date cannot be after defaults.end_date"
            )
        return self


class FlowStageSpec(BaseModel):
    """Single stage definition in a flow spec."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(description="Stable stage identifier in this flow.")
    pipeline: Literal["retrieve", "chat", "exhibit"] = Field(
        description="Pipeline executed by this stage.",
    )
    overrides: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Stage-level config overrides merged over defaults.",
    )
    condition: Literal["always", "previous_success", "previous_has_outputs"] = (
        Field(
            default="always",
            description="Execution condition relative to previous stage result.",
        )
    )
    seed_from_stage: str | None = Field(
        default=None,
        description="Optional upstream retrieve stage ID used for chat seeded context.",
    )

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("stage id cannot be empty")
        return cleaned


class FlowSpec(BaseModel):
    """Top-level multi-stage flow specification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        default="retrieve_chat_flow",
        description="Human-readable name for the flow definition.",
    )
    defaults: FlowDefaults = Field(
        description="Shared defaults inherited by stage configs.",
    )
    stages: list[FlowStageSpec] = Field(
        default_factory=list,
        description="Ordered stage execution plan.",
    )
    on_failure: Literal["stop", "continue"] = Field(
        default="stop",
        description="Flow behavior after a stage failure.",
    )

    @model_validator(mode="after")
    def _validate_stage_graph(self) -> FlowSpec:
        if not self.stages:
            raise ValueError("flow spec requires at least one stage")

        stage_ids: set[str] = set()
        stage_pipelines: dict[str, str] = {}
        for stage in self.stages:
            if stage.id in stage_ids:
                raise ValueError(f"duplicate stage id '{stage.id}'")
            stage_ids.add(stage.id)
            stage_pipelines[stage.id] = stage.pipeline

        for stage in self.stages:
            if stage.seed_from_stage is None:
                continue
            if stage.pipeline != "chat":
                raise ValueError(
                    f"stage '{stage.id}' sets seed_from_stage but is not chat"
                )
            if stage.seed_from_stage not in stage_ids:
                raise ValueError(
                    f"stage '{stage.id}' references unknown seed stage '{stage.seed_from_stage}'"
                )
            upstream_pipeline = stage_pipelines.get(stage.seed_from_stage)
            if upstream_pipeline != "retrieve":
                raise ValueError(
                    f"stage '{stage.id}' seed_from_stage must reference a retrieve stage"
                )
        return self


class FlowStageResult(BaseModel):
    """Execution result for one stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_id: str
    pipeline: str
    success: bool
    skipped: bool = False
    error: str | None = None
    duration_seconds: float = 0.0
    run_id: str | None = None
    run_short_id: int | None = None
    outputs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class FlowRunResult(BaseModel):
    """Aggregate result for a full flow run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    flow_run_id: str
    flow_name: str
    success: bool
    stage_results: list[FlowStageResult] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


type FlowResult = FlowRunResult
