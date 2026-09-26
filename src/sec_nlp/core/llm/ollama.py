# src/sec_nlp/core/llm/ollama.py
"""Ollama model client construction and embedding setup helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_ollama.llms import OllamaLLM


import os
from typing import TypedDict, Unpack

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import JsonValue

_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaKwargs(TypedDict, total=False):
    """Optional generation controls forwarded to the Ollama client."""

    reasoning: bool | None
    validate_model_on_init: bool
    mirostat: int | None
    mirostat_eta: float | None
    mirostat_tau: float | None
    num_ctx: int | None
    num_gpu: int | None
    num_thread: int | None
    num_predict: int | None
    repeat_last_n: int | None
    repeat_penalty: float | None
    seed: int | None
    stop: list[str] | None
    tfs_z: float | None
    keep_alive: int | str | None
    base_url: str | None
    client_kwargs: dict[str, JsonValue] | None
    async_client_kwargs: dict[str, JsonValue] | None
    sync_client_kwargs: dict[str, JsonValue] | None


def build_ollama_llm(
    model_name: str,
    base_url: str | None = None,
    temperature: float = 0.1,
    top_k: int = 10,
    top_p: float = 0.5,
    **kwargs: Unpack[OllamaKwargs],
) -> OllamaLLM:
    """
    Factory function to create an Ollama LLM runnable.

    Args:
        model_name: Ollama model name (e.g., "llama3.2", "mistral")
        base_url: Ollama server URL (defaults to http://localhost:11434)
        temperature: Sampling temperature
        **kwargs: Additional parameters for OllamaLLM

    Returns:
        OllamaLLM: LLM object that implements Runnable[str | PromptValue, str]
    """

    base_url = resolve_ollama_base_url(base_url)

    # Apply performance defaults: keep model resident and offload all layers to GPU
    if "keep_alive" not in kwargs:
        kwargs["keep_alive"] = -1
    if "num_gpu" not in kwargs:
        kwargs["num_gpu"] = -1

    from langchain_ollama.llms import OllamaLLM

    ollama_llm = OllamaLLM(
        model=model_name,
        base_url=base_url,
        temperature=temperature,
        top_k=top_k,
        top_p=top_p,
        **kwargs,
    )

    logger.info(
        "Created Ollama LLM: model=%s, base_url=%s", model_name, base_url
    )

    return ollama_llm


def resolve_ollama_base_url(base_url: str | None = None) -> str:
    """Resolve Ollama base URL from explicit value or environment."""
    if base_url is not None and base_url.strip():
        return base_url
    configured_url = os.getenv("SEC_NLP_OLLAMA_BASE_URL")
    if configured_url is not None and configured_url.strip():
        return configured_url
    legacy_url = os.getenv("OLLAMA_BASE_URL")
    if legacy_url is not None and legacy_url.strip():
        return legacy_url
    return _DEFAULT_OLLAMA_BASE_URL
