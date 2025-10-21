import abc
from typing import Any

from _typeshed import Incomplete

from sec_nlp.core.config import get_logger as get_logger
from sec_nlp.core.llm.base import LocalLLMBase as LocalLLMBase

logger: Incomplete

class FlanT5LocalLLM(LocalLLMBase, metaclass=abc.ABCMeta):
    model_name: str
    do_sample: bool
    top_p: float
    device: str | None
    eos_token_id: int | None
    def model_post_init(self, _ctx: Any) -> None: ...
