from collections.abc import Callable

from langchain_core.prompts import PromptTemplate

from .conftest import FakeLLM


def test_llm_passthrough(fake_llm: Callable[[bool], FakeLLM]) -> None:
    """Test that uninitialized FakeLLM returns prompt passthrough."""
    ...


def test_llm_generate(fake_llm: Callable[[bool], FakeLLM]) -> None:
    """Test that initialized FakeLLM calls _generate()."""
    llm = fake_llm(True)
    result = llm.invoke("hi")
    assert result == "call:hi"
