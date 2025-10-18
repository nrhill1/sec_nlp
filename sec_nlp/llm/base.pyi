from typing import Any, Protocol

from langchain_core.runnables import Runnable, RunnableConfig

class LocalLLM(Runnable[str, str], Protocol):
    model_name: str
    max_new_tokens: int
    temperature: float

    def invoke(self, input: str, config: RunnableConfig | None = None, **kwargs: Any) -> str: ...
    def batch(
        self,
        inputs: list[str],
        config: RunnableConfig | list[RunnableConfig] | None = None,
        **kwargs: Any,
    ) -> list[str]: ...
