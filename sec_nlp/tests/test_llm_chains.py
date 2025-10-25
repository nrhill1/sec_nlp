from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import LLM
from langchain_core.prompts import BasePromptTemplate, PromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig

from sec_nlp.core.llm.chains import SummarizationOutput, build_summarization_runnable

from .conftest import FakeLLM


def test_chain_invoke_json_mode(fake_llm: Callable[bool, FakeLLM]) -> None:
    prompt: BasePromptTemplate[Any] = PromptTemplate.from_template("{chunk}")

    llm: LLM = fake_llm(True)

    chain: Runnable[Any, Any] = build_summarization_runnable(
        prompt=prompt,
        llm=llm,
        require_json=True,
    )

    out = chain.invoke({"symbol": "AAPL", "chunk": "Revenue...", "search_term": "revenue"})
    assert isinstance(out, SummarizationOutput)
    assert isinstance(out.confidence, float)
    assert isinstance(out.points, list)
    assert isinstance(out.summary, str)
    assert out.error is None
    assert out.raw_output is None
