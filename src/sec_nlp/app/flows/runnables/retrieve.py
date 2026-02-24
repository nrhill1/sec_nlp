# src/sec_nlp/app/flows/runnables/retrieve.py
"""Retrieve stage runnable for flow execution."""

from __future__ import annotations

from time import perf_counter

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowStageResult,
    FlowStageSpec,
)
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)
from sec_nlp.types import JsonValue

from .utils import (
    StageConfigValue,
    build_stage_defaults_payload,
    build_stage_result,
)


class RetrieveFlowInvokeInput(BaseModel):
    """Typed invoke payload for retrieve stage runnable."""

    model_config = ConfigDict(frozen=True, extra="forbid")


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
        payload: dict[str, StageConfigValue] = build_stage_defaults_payload(
            self.defaults
        )
        payload.update(self.stage.overrides)
        started = perf_counter()
        pipeline_config = RetrieveSettings.model_validate(payload)
        pipeline = RetrievePipeline(config=pipeline_config)
        result, seed_bundle = pipeline.run_for_flow()
        elapsed = perf_counter() - started
        if result.success:
            self.artifacts.put_retrieve_seed(self.stage.id, seed_bundle)

        return build_stage_result(
            stage=self.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=str(pipeline_config.run_id),
            run_short_id=pipeline_config.short_id,
        )
