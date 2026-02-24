# src/sec_nlp/app/flows/runnables/chat.py
"""Chat stage runnable for flow execution."""

from __future__ import annotations

from time import perf_counter

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowStageInputBinding,
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
    defaults: FlowDefaults | None = Field(
        default=None,
        description="Optional shared defaults merged into stage config payloads.",
    )
    artifacts: FlowArtifactStore = Field(
        description="In-memory artifact store shared across flow stages.",
    )
    compiled_config: ChatSettings | None = Field(
        default=None,
        description="Prevalidated chat settings compiled once per flow run.",
        exclude=True,
    )

    @staticmethod
    def _answer_preview(answer: str, *, max_chars: int = 160) -> str:
        """Build a compact single-line answer preview for flow logging."""
        normalized = " ".join(answer.split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1].rstrip()}…"

    @staticmethod
    def _resolve_seed_binding(
        stage: FlowStageSpec,
    ) -> tuple[str | None, str | None]:
        """Resolve retrieve-seed source stage and validate chat input bindings."""
        resolved: str | None = None
        for binding in stage.inputs:
            binding_error = ChatFlowRunnable._validate_input_binding(
                stage=stage,
                binding=binding,
            )
            if binding_error is not None:
                return None, binding_error
            if resolved is not None:
                return (
                    None,
                    f"chat stage '{stage.id}' accepts at most one retrieve_seed input",
                )
            resolved = binding.from_stage

        return resolved, None

    @staticmethod
    def _validate_input_binding(
        *,
        stage: FlowStageSpec,
        binding: FlowStageInputBinding,
    ) -> str | None:
        """Validate one input binding against current chat-stage capabilities."""
        if binding.artifact != "retrieve_seed":
            return (
                f"chat stage '{stage.id}' does not support input artifact "
                f"'{binding.artifact}'"
            )
        if (
            binding.target_field is not None
            and binding.target_field != "seed_context"
        ):
            return (
                f"chat stage '{stage.id}' retrieve_seed binding target_field "
                "must be 'seed_context'"
            )
        return None

    def invoke(
        self,
        input: ChatFlowInvokeInput | None = None,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> FlowStageResult:
        """Run chat stage with optional seeded context from retrieve."""
        _ = input
        _ = config
        _ = kwargs
        seed_source, seed_error = self._resolve_seed_binding(self.stage)
        if seed_error is not None:
            return build_unexecuted_stage_result(
                stage=self.stage,
                success=False,
                skipped=False,
                error=seed_error,
            )

        seed_bundle = None
        if seed_source is not None:
            seed_bundle = self.artifacts.get_chat_seed(seed_source)
            if seed_bundle is None:
                return build_unexecuted_stage_result(
                    stage=self.stage,
                    success=False,
                    skipped=False,
                    error=(
                        f"Missing seeded artifact from stage '{seed_source}'"
                    ),
                )

        started = perf_counter()
        if self.compiled_config is not None:
            pipeline_config = self.compiled_config
            if seed_bundle is not None:
                pipeline_config = pipeline_config.model_copy(
                    update={"seed_context": seed_bundle}
                )
        else:
            if self.defaults is None:
                raise ValueError(
                    "chat runnable requires defaults when compiled_config "
                    "is not supplied"
                )
            payload: dict[str, ChatStageConfigValue] = (
                build_chat_defaults_payload(self.defaults)
            )
            payload.update(self.stage.overrides)
            if seed_bundle is not None:
                payload["seed_context"] = seed_bundle
            pipeline_config = ChatSettings.model_validate(payload)

        result = ChatPipeline(config=pipeline_config).run()
        elapsed = perf_counter() - started

        stage_result = build_stage_result(
            stage=self.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=str(pipeline_config.run_id),
            run_short_id=pipeline_config.short_id,
        )
        if result.success and isinstance(result.answer, str) and result.answer:
            metadata = dict(stage_result.metadata)
            metadata["answer_preview"] = self._answer_preview(result.answer)
            stage_result = stage_result.model_copy(
                update={"metadata": metadata}
            )
        return stage_result
