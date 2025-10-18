# sec_nlp/pipelines/utils/llms/ollama_factory.py
from __future__ import annotations

import logging
import os

from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)


def build_ollama_llm(
    model_name: str,
    base_url: str | None = None,
    temperature: float = 0.1,
    **kwargs,
) -> Runnable[str, str]:
    """
    Factory function to create an Ollama LLM runnable.

    Args:
        model_name: Ollama model name (e.g., "llama3.2", "mistral")
        base_url: Ollama server URL (defaults to http://localhost:11434)
        temperature: Sampling temperature
        **kwargs: Additional parameters for OllamaLLM

    Returns:
        OllamaLLM: LLM object that implements <Runnable[str, str]>
    """
    try:
        from langchain_ollama import OllamaLLM
    except ImportError as e:
        raise ImportError(
            "langchain-ollama not installed. Run: uv pip install langchain-ollama"
        ) from e

    base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    llm = OllamaLLM(
        model=model_name,
        base_url=base_url,
        temperature=temperature,
        **kwargs,
    )

    logger.info("Created Ollama LLM: model=%s, base_url=%s", model_name, base_url)
    return llm
