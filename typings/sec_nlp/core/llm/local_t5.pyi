from typing import Any

from _typeshed import Incomplete
from langchain_core.callbacks.manager import CallbackManagerForLLMRun as CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM

from sec_nlp.core.config import get_logger as get_logger

logger: Incomplete

class FlanT5LocalLLM(LLM):
    model_name: str
    max_new_tokens: int
    do_sample: bool
    temperature: float
    top_p: float
    device: str | None
    eos_token_id: int | None
    _torch: Any
    _tokenizer: Any
    _model: Any
    def __init__(self, **kwargs: Any) -> None: ...
    def _initialize_model(self) -> None: ...
    @property
    def _llm_type(self) -> str: ...
    @property
    def _identifying_params(self) -> dict[str, Any]: ...
    def _call(
        self,
        prompt: str,
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str: ...
