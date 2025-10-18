from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BaseLLM(BaseModel, Runnable[str, str], ABC):
    """
    Abstract base class for all LLM implementations.

    Provides common interface for both local (HuggingFace) and API-based (Ollama) models.
    """

    name: str = Field(default="base-llm", description="LLM name")
    model_name: str = Field(..., description="Model identifier")
    max_new_tokens: int = Field(default=512, description="Maximum tokens to generate")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature")

    class Config:
        arbitrary_types_allowed = True

    @abstractmethod
    def invoke(self, input: str, config: RunnableConfig | None = None, **kwargs: Any) -> str:
        """
        Generate text from input prompt.

        Args:
            input: Input prompt text
            config: Optional runtime configuration
            **kwargs: Additional generation arguments

        Returns:
            Generated text
        """
        ...

    def batch(
        self,
        inputs: list[str],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """
        Generate text for multiple prompts.

        Args:
            inputs: List of input prompts
            config: Optional runtime configuration(s)
            **kwargs: Additional generation arguments

        Returns:
            List of generated texts
        """
        if isinstance(config, list):
            if len(config) != len(inputs):
                raise ValueError(f"len(config)={len(config)} must equal len(inputs)={len(inputs)}")
            return [
                self.invoke(inp, cfg, **kwargs) for inp, cfg in zip(inputs, config, strict=True)
            ]
        return [self.invoke(inp, config, **kwargs) for inp in inputs]
