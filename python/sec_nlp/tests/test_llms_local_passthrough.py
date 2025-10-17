from collections.abc import Callable

from sec_nlp.tests.conftest import DummyLLM


def test_llm_passthrough(dummy_llm: Callable[[bool], DummyLLM]) -> None:
    """Test that uninitialized DummyLLM returns prompt passthrough."""
    llm = dummy_llm(False)
    result = llm.invoke("hi")
    assert result == "hi"


def test_llm_generate(dummy_llm: Callable[[bool], DummyLLM]) -> None:
    """Test that initialized DummyLLM calls _generate()."""
    llm = dummy_llm(True)
    result = llm.invoke("hi")
    assert result == "gen:hi"
