"""Chat stage runnable for flow execution."""

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
from sec_nlp.pipelines.presets.chat import ChatPipeline, ChatSettings
from sec_nlp.types import JsonValue

from .utils import (
    ChatStageConfigValue,
    build_chat_defaults_payload,
    build_stage_result,
    build_unexecuted_stage_result,
)


class ChatFlowInvokeInput(BaseModel):
    """Typed invoke payload for chat stage runnable."""

    model_config = ConfigDict(frozen=True, extra="forbid")


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
        payload: dict[str, ChatStageConfigValue] = build_chat_defaults_payload(
            self.defaults
        )
        payload.update(self.stage.overrides)

        if self.stage.seed_from_stage is not None:
            seed_bundle = self.artifacts.get_chat_seed(
                self.stage.seed_from_stage
            )
            if seed_bundle is None:
                return build_unexecuted_stage_result(
                    stage=self.stage,
                    success=False,
                    skipped=False,
                    error=(
                        f"Missing seeded artifact from stage "
                        f"'{self.stage.seed_from_stage}'"
                    ),
                )
            payload["seed_context"] = seed_bundle

        started = perf_counter()
        pipeline_config = ChatSettings.model_validate(payload)
        result = ChatPipeline(config=pipeline_config).run()
        elapsed = perf_counter() - started

        return build_stage_result(
            stage=self.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=str(pipeline_config.run_id),
            run_short_id=pipeline_config.short_id,
        )
