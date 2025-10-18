from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from sec_nlp.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class OllamaLLM(BaseLLM):
    """
    Ollama LLM wrapper using REST API.

    Supports any model available in your Ollama installation:
    - llama3.2, llama3.1, llama3
    - mistral, mixtral
    - phi3
    - gemma, gemma2
    - qwen, qwen2
    - codellama, deepseek-coder

    No intermediate API class needed - implements invoke() directly.
    """

    model_name: str = Field(default="llama3.2", description="Ollama model name")
    base_url: str = Field(default="http://localhost:11434", description="Ollama API base URL")
    timeout: int = Field(default=300, description="Request timeout in seconds")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="Nucleus sampling")
    top_k: int = Field(default=40, ge=0, description="Top-k sampling")
    stream: bool = Field(default=False, description="Stream responses")

    def invoke(self, input: str, config: Any | None = None, **kwargs: Any) -> str:
        """
        Generate text using Ollama API.

        Args:
            input: Input prompt
            config: Runtime configuration (unused)
            **kwargs: Additional generation arguments

        Returns:
            Generated text

        Raises:
            RuntimeError: If the API request fails
        """
        ...
