from __future__ import annotations

import json
from typing import Any

from langchain_core.prompts import BasePromptTemplate, PromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig

from sec_nlp.llm.base import LocalLLM
from sec_nlp.llm.chains import build_summarization_runnable


class DummyLocalLLM(LocalLLM):
    """Minimal LocalLLM for tests: always returns a JSON string that the chain parses."""

    def __init__(self, model_name: str = "dummy", **_: Any) -> None:
        super().__init__(model_name=model_name)

    def _load_backend(self) -> None:
        self._model = None  # type: ignore[attr-defined]
        self._tokenizer = None  # type: ignore[attr-defined]

    def _generate(self, prompt: str, gen_kwargs: dict[str, Any]) -> str:
        return prompt

    # Match Runnable[str, str] signature
    def invoke(self, input: str, config: RunnableConfig | None = None, **__: Any) -> str:
        return json.dumps({"summary": "ok", "points": ["x"], "confidence": 0.7})


def test_chain_invoke_json_mode() -> None:
    prompt: BasePromptTemplate = PromptTemplate.from_template("{chunk}")

    llm: LocalLLM = DummyLocalLLM()

    chain: Runnable[Any, Any] = build_summarization_runnable(
        prompt=prompt,
        llm=llm,
        require_json=True,
    )

    out = chain.invoke({"symbol": "AAPL", "chunk": "Revenue...", "search_term": "revenue"})
    assert isinstance(out, dict)
    assert out["status"] == "ok"
    assert out["summary"]["summary"] == "ok"
