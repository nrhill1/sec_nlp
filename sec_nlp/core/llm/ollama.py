# sec_nlp/pipelines/utils/llm/ollama_factory.py
from __future__ import annotations

import os
from typing import Any

from langchain_ollama.llms import OllamaLLM

from sec_nlp.core.config import get_logger

logger = get_logger(__name__)


def build_ollama_llm(
    model_name: str,
    base_url: str | None = None,
    temperature: float = 0.1,
    **kwargs: Any,
) -> OllamaLLM:
    """
    Factory function to create an Ollama LLM runnable.

    Args:
        model_name: Ollama model name (e.g., "llama3.2", "mistral")
        base_url: Ollama server URL (defaults to http://localhost:11434)
        temperature: Sampling temperature
        **kwargs: Additional parameters for OllamaLLM

    Returns:
        OllamaLLM: LLM object that implements <Runnable[str | PromptValue, str]>
    """

    base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    llm = OllamaLLM(model=model_name, base_url=base_url, temperature=temperature, **kwargs)

    logger.info("Created Ollama LLM: model=%s, base_url=%s", model_name, base_url)
    return llm
