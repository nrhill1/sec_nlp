from uuid import UUID

from _typeshed import Incomplete
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult as LLMResult

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.types import (
    MetadataMap as MetadataMap,
    MetadataValue as MetadataValue,
)

class TracingCallbackHandler(BaseCallbackHandler):
    log_prompts: Incomplete
    def __init__(self, log_prompts: bool = False) -> None: ...
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
    ) -> None: ...
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: MetadataValue,
    ) -> None: ...
    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: MetadataValue,
    ) -> None: ...
