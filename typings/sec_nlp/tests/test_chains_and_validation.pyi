from collections.abc import Callable as Callable

from langchain_core.language_models import LLM as LLM
from langchain_core.prompts import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from langchain_core.runnables import RunnableConfig as RunnableConfig

from sec_nlp.core.llm.chains import SummarizationOutput as SummarizationOutput
from sec_nlp.core.llm.chains import build_summarization_runnable as build_summarization_runnable

from .conftest import FakeLLM as FakeLLM

def test_chain_invoke_json_mode(fake_llm: Callable[bool, FakeLLM]) -> None: ...
