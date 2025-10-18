# sec_nlp/llm/__init__.py
"""LLM integrations."""

from sec_nlp.llm.base import LocalLLM
from sec_nlp.llm.local_t5 import FlanT5LocalLLM
from sec_nlp.llm.ollama import OllamaLLM

__all__: list[str] = ["LocalLLM", "FlanT5LocalLLM", "OllamaLLM"]
