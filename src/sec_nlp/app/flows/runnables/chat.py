"""Chat stage runnable for flow execution."""

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
from sec_nlp.pipelines.presets.chat import (
    ChatPipeline,
    ChatSeedBundle,
    ChatSettings,
)
from sec_nlp.types import JsonValue

type StageConfigValue = JsonValue | date | Path | ChatSeedBundle


class ChatFlowInvokeInput(BaseModel):
    """Typed invoke payload for chat stage runnable."""

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


class ChatFlowRunnable(
    RunnableSerializable[ChatFlowInvokeInput, FlowStageResult]
):
    """Runnable adapter that executes a chat stage."""

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
        input: ChatFlowInvokeInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> FlowStageResult:
        """Run chat stage with optional seeded context from retrieve."""
        _ = input
        _ = config
        _ = kwargs
        payload = _defaults_payload(self.defaults)
        payload.update(self.stage.overrides)

        if self.stage.seed_from_stage is not None:
            seed_bundle = self.artifacts.get_chat_seed(
                self.stage.seed_from_stage
            )
            if seed_bundle is None:
                return FlowStageResult(
                    stage_id=self.stage.id,
                    pipeline=self.stage.pipeline,
                    success=False,
                    skipped=False,
                    error=(
                        f"Missing seeded artifact from stage "
                        f"'{self.stage.seed_from_stage}'"
                    ),
                    duration_seconds=0.0,
                    outputs=[],
                    metadata={},
                )
            payload["seed_context"] = seed_bundle

        started = perf_counter()
        pipeline_config = ChatSettings.model_validate(payload)
        result = ChatPipeline(config=pipeline_config).run()
        elapsed = perf_counter() - started

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
