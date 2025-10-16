# sec_nlp/llms/local_llm_base.py
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, Field, PrivateAttr

logger = logging.getLogger(__name__)


class LocalLLM(BaseModel, Runnable[str, str], ABC):
    """
    Base class for local-only HF models that plugs directly into LangChain as a Runnable.
    """

    name: str = Field(default="local-llm", description="LLM base class name")
    model_name: str = Field(..., description="HF model id or local path")
    max_new_tokens: int = 512
    do_sample: bool = False
    temperature: float = 0.0
    top_p: float = 1.0
    device: str | None = Field(default=None, description="e.g. 'cuda', 'cpu', 'mps'")
    eos_token_id: int | None = None

    _tokenizer: Any | None = PrivateAttr(default=None)
    _model: Any | None = PrivateAttr(default=None)
    _torch: Any | None = PrivateAttr(default=None)

    @staticmethod
    def _lazy_imports() -> bool:
        try:
            import torch  # noqa: F401
            from transformers import AutoTokenizer  # noqa: F401

            return True
        except Exception as e:
            logger.error("Transformers/torch not available: %s", e)
            return False

    def model_post_init(self, __ctx: Any) -> None:
        if not self._lazy_imports():
            return
        from transformers import AutoTokenizer
        import torch

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, use_fast=True)  # type: ignore
        self._load_backend()

        if self.device is not None and self._model is not None:
            self._model.to(self.device)

        logger.info("Initialized %s with %s", self.__class__.__name__, self.model_name)

    def invoke(self, input: str, config: RunnableConfig | None = None, **kwargs: Any) -> str:
        if self._model is None or self._tokenizer is None:
            logger.warning("Model not initialized; returning prompt passthrough.")
            return input
        return self._generate(input, kwargs or {})

    def batch(
        self,
        inputs: list[str],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        **kwargs: Any | None,
    ) -> list[str]
        if isinstance(config, list):
            if len(config) != len(inputs):
                raise ValueError(f"len(config)={len(config)} must equal len(inputs)={len(inputs)}")
            return [self.invoke(inp, cfg, **kwargs) for inp, cfg in zip(inputs, config)]


        return [self.invoke(inp, config, **kwargs) for inp in inputs]

    @abstractmethod
    def _load_backend(self) -> None: ...

    @abstractmethod
    def _generate(self, prompt: str, gen_kwargs: dict[str, Any]) -> str: ...
