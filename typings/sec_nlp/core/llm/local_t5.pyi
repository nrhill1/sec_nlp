from .base import LocalLLMBase as LocalLLMBase
from _typeshed import Incomplete
from sec_nlp.core.config import get_logger as get_logger
from typing import Any

logger: Incomplete

class FlanT5LocalLLM(LocalLLMBase):
    model_name: str
    do_sample: bool
    top_p: float
    device: str | None
    eos_token_id: int | None
    _torch: Incomplete
    _tokenizer: Incomplete
    _model: Incomplete
    def model_post_init(self, _ctx: Any) -> None: ...
    def _load_backend(self) -> None: ...
    def _generate(self, prompt: str, gen_kwargs: dict[str, Any]) -> str: ...
