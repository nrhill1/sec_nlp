from functools import cached_property as cached_property
from pathlib import Path

from _typeshed import Incomplete
from langchain_ollama.llms import OllamaLLM as OllamaLLM
from pydantic import BaseModel

from sec_nlp.core.llm.ollama import OllamaKwargs as OllamaKwargs

class LLMConfig(BaseModel):
    model_config: Incomplete
    model_name: str
    base_url: str | None
    timeout: int
    prompt_file: Path | None
    max_new_tokens: int
    temperature: float
    require_json: bool
    ollama_kwargs: OllamaKwargs
    @cached_property
    def prompt_path(self) -> Path: ...
    def setup_ollama_model(self) -> OllamaLLM: ...
