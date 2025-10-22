# sec_nlp/corellm/__init__.py
"""Langchain LLM integrations."""

from sec_nlp.core.llm.chains import (
    SummarizationInput,
    SummarizationOutput,
    build_summarization_runnable,
)
from sec_nlp.core.llm.local_t5 import FlanT5LocalLLM
from sec_nlp.core.llm.ollama import build_ollama_llm

__all__: list[str] = [
    "FlanT5LocalLLM",
    "build_ollama_llm",
    "SummarizationInput",
    "SummarizationOutput",
    "build_summarization_runnable",
]
