from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import LLM
from langchain_core.prompts import BasePromptTemplate, PromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig

from sec_nlp.core.llm.chains import build_summarization_runnable


def test_chain_invoke_json_mode(fake_llm) -> None:
    prompt: BasePromptTemplate[Any] = PromptTemplate.from_template("{chunk}")

    llm: LLM = fake_llm(True)

    chain: Runnable[Any, Any] = build_summarization_runnable(
        prompt=prompt,
        llm=llm,
        require_json=True,
    )

    out = chain.invoke({"symbol": "AAPL", "chunk": "Revenue...", "search_term": "revenue"})
    assert isinstance(out, dict)
    assert out["status"] == "ok"
    assert out["summary"]["summary"] == "ok"
