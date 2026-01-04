# src/sec_nlp/pipelines/presets/analyze/callbacks.py
"""LangChain callback handlers for the analyze pipeline."""

from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.types import MetadataMap, MetadataValue


class TracingCallbackHandler(BaseCallbackHandler):
    """Lightweight LangChain callback handler for logging/tracing."""

    def __init__(self, log_prompts: bool = False) -> None:
        self.log_prompts = log_prompts

    def on_llm_start(
        self,
        serialized: MetadataMap,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: MetadataMap | None = None,
        **kwargs: MetadataValue,
    ) -> None:
        model = serialized.get("name") or serialized.get("id")
        model_label = str(model) if model is not None else "unknown"
        logger.info("LLM start: model=%s prompts=%d", model_label, len(prompts))
        if self.log_prompts:
            for idx, prompt in enumerate(prompts):
                logger.debug("Prompt[%d]: %s", idx, prompt)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: MetadataValue,
    ) -> None:
        logger.info("LLM end: response received")

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: MetadataValue,
    ) -> None:
        logger.error(
            "LLM error: %s (run_id=%s parent=%s)",
            error,
            run_id,
            parent_run_id,
        )
