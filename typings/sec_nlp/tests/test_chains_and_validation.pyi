from langchain_core.language_models import LLM as LLM
from langchain_core.prompts import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from langchain_core.runnables import RunnableConfig as RunnableConfig

from sec_nlp.core.llm.chains import build_summarization_runnable as build_summarization_runnable

from .conftest import dummy_llm as dummy_llm

def test_chain_invoke_json_mode() -> None: ...
