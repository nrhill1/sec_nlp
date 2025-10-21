from typing import Any

from langchain_core.prompts import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from langchain_core.runnables import RunnableConfig as RunnableConfig

from sec_nlp.core.llm.base import LocalLLMBase as LocalLLMBase
from sec_nlp.core.llm.chains import build_summarization_runnable as build_summarization_runnable

class DummyLocalLLM(LocalLLMBase):
    def __init__(self, model_name: str = "dummy", **_: Any) -> None: ...
    def invoke(self, input: str, config: RunnableConfig | None = None, **__: Any) -> str: ...

def test_chain_invoke_json_mode() -> None: ...
