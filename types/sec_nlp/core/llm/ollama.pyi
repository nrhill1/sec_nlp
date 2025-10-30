from typing import Any

from _typeshed import Incomplete
from langchain_ollama.llms import OllamaLLM

from sec_nlp.core import get_logger as get_logger

logger: Incomplete

def build_ollama_llm(
    model_name: str,
    base_url: str | None = None,
    temperature: float = 0.1,
    **kwargs: Any,
) -> OllamaLLM: ...
