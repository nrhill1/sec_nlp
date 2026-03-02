# src/sec_nlp/core/llm/__init__.py
"""LangChain LLM client construction and chain-building helpers."""

from .chains import build_runnable
from .ollama import build_ollama_llm

__all__: tuple[str, ...] = (
    "build_ollama_llm",
    "build_runnable",
)
