from collections.abc import Callable as Callable

from langchain_core.prompts import PromptTemplate as PromptTemplate

from .conftest import FakeLLM as FakeLLM

def test_llm_passthrough(fake_llm: Callable[[bool], FakeLLM]) -> None: ...
def test_llm_generate(fake_llm: Callable[[bool], FakeLLM]) -> None: ...
