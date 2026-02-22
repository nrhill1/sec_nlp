"""Retrieve stage runnable for flow execution."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from time import perf_counter

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowStageResult,
    FlowStageSpec,
)
from sec_nlp.core.types import coerce_result_json_value
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)
from sec_nlp.types import JsonValue

type StageConfigValue = JsonValue | date | Path


class RetrieveFlowInvokeInput(BaseModel):
    """Typed invoke payload for retrieve stage runnable."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _defaults_payload(defaults: FlowDefaults) -> dict[str, StageConfigValue]:
    payload: dict[str, StageConfigValue] = {"email": defaults.email}
    if defaults.symbols:
        payload["symbols"] = list(defaults.symbols)
    if defaults.forms is not None:
        payload["forms"] = list(defaults.forms)
    if defaults.start_date is not None:
        payload["start_date"] = defaults.start_date
    if defaults.end_date is not None:
        payload["end_date"] = defaults.end_date
    if defaults.dl_path is not None:
        payload["dl_path"] = defaults.dl_path
    if defaults.out_path is not None:
        payload["out_path"] = defaults.out_path
    if defaults.dry_run is not None:
        payload["dry_run"] = defaults.dry_run
    return payload


class RetrieveFlowRunnable(
    RunnableSerializable[RetrieveFlowInvokeInput, FlowStageResult]
):
    """Runnable adapter that executes a retrieve stage."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
        defer_build=True,
    )

    stage: FlowStageSpec = Field(
        description="Flow stage specification for this runnable execution.",
    )
    defaults: FlowDefaults = Field(
        description="Shared defaults merged into stage config payloads.",
    )
    artifacts: FlowArtifactStore = Field(
        description="In-memory artifact store shared across flow stages.",
    )

    def invoke(
        self,
        input: RetrieveFlowInvokeInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> FlowStageResult:
        """Run retrieve stage and cache handoff artifacts for downstream chat."""
        _ = input
        _ = config
        _ = kwargs
        payload = _defaults_payload(self.defaults)
        payload.update(self.stage.overrides)
        started = perf_counter()
        pipeline_config = RetrieveSettings.model_validate(payload)
        pipeline = RetrievePipeline(config=pipeline_config)
        result, seed_bundle = pipeline.run_for_flow()
        elapsed = perf_counter() - started
        if result.success:
            self.artifacts.put_retrieve_seed(self.stage.id, seed_bundle)

        metadata: dict[str, JsonValue] = {}
        for key, value in result.metadata.items():
            normalized = coerce_result_json_value(value)
            if isinstance(key, str) and normalized is not None:
                metadata[key] = normalized

        return FlowStageResult(
            stage_id=self.stage.id,
            pipeline=self.stage.pipeline,
            success=result.success,
            skipped=False,
            error=result.error,
            duration_seconds=elapsed,
            run_id=str(pipeline_config.run_id),
            run_short_id=(
                pipeline_config.short_id
                if pipeline_config.short_id > 0
                else None
            ),
            outputs=[str(path) for path in result.outputs],
            metadata=metadata,
        )
