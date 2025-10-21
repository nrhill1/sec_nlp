import abc
from _typeshed import Incomplete
from abc import ABC, abstractmethod
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable, RunnableConfig as RunnableConfig
from pydantic import BaseModel
from sec_nlp.core.config import get_logger as get_logger
from typing import Any

logger: Incomplete

class LocalLLMBase(BaseModel, Runnable[str | PromptValue, str], ABC, metaclass=abc.ABCMeta):
    name: str
    model_name: str
    max_new_tokens: int
    do_sample: bool
    temperature: float
    top_p: float
    device: str | None
    eos_token_id: int | None
    _tokenizer: Any | None
    _model: Any | None
    _torch: Any | None
    @staticmethod
    def _lazy_imports() -> bool: ...
    def model_post_init(self, /, __ctx: Any) -> None: ...
    def input_to_string(self, input: str | PromptValue) -> str: ...
    def invoke(self, input: str | PromptValue, config: RunnableConfig | None = None, **kwargs: Any) -> str: ...
    def batch(self, inputs: list[str | PromptValue], config: RunnableConfig | list[RunnableConfig] | None = None, **kwargs: Any) -> list[str]: ...
    @abstractmethod
    def _load_backend(self) -> None: ...
    @abstractmethod
    def _generate(self, prompt: str, gen_kwargs: dict[str, Any]) -> str: ...
