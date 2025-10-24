from collections.abc import Callable

from .conftest import FakeLLM


def test_llm_passthrough(fake_llm: Callable[[bool], FakeLLM]) -> None:
    """Test that uninitialized FakeLLM returns prompt passthrough."""
    llm = fake_llm(False)
    result = llm.invoke("hi")
    assert result == "hi"


def test_llm_generate(fake_llm: Callable[[bool], FakeLLM]) -> None:
    """Test that initialized FakeLLM calls _generate()."""
    llm = fake_llm(True)
    result = llm.invoke("hi")
    assert result == "gen:hi"
