from typing import TypedDict, Unpack

from langchain_ollama.llms import OllamaLLM

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.types import JsonValue as JsonValue

class OllamaKwargs(TypedDict, total=False):
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
) -> OllamaLLM: ...
