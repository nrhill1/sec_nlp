# src/sec_nlp/app/flows/runnables/exhibit.py
"""Exhibit stage runnable for flow execution."""

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
from sec_nlp.pipelines.presets.exb import ExhibitConfig, ExhibitPipeline
from sec_nlp.types import JsonValue

from .utils import (
    StageConfigValue,
    build_stage_defaults_payload,
    build_stage_result,
)


class ExhibitFlowInvokeInput(BaseModel):
    """Typed invoke payload for exhibit stage runnable."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ExhibitFlowRunnable(
    RunnableSerializable[ExhibitFlowInvokeInput, FlowStageResult]
):
    """Runnable adapter that executes an exhibit stage."""

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
        input: ExhibitFlowInvokeInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> FlowStageResult:
        """Run exhibit stage and cache contract evidence artifacts."""
        _ = input
        _ = config
        _ = kwargs
        payload: dict[str, StageConfigValue] = build_stage_defaults_payload(
            self.defaults
        )
        payload.update(self.stage.overrides)
        started = perf_counter()
        pipeline_config = ExhibitConfig.model_validate(payload)
        pipeline = ExhibitPipeline(config=pipeline_config)
        result, evidence_bundle = pipeline.run_for_flow()
        elapsed = perf_counter() - started
        if result.success:
            self.artifacts.put_contract_evidence(self.stage.id, evidence_bundle)

        return build_stage_result(
            stage=self.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=str(pipeline_config.run_id),
            run_short_id=pipeline_config.short_id,
        )
