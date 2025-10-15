from sec_nlp.chains.sec_runnable import build_sec_runnable
from some_module import Runnable


def test_chain_invoke_json_mode():
    class FakePrompt:
        def __or__(self, other):
            return other

        def __ror__(self, other):
            return self

    class FakeLLM(Runnable):
        def __or__(self, other):
            return other

        def __ror__(self, other):
            return self

        def invoke(self, prompt, **_):
            return '{"summary":"ok","points":["x"],"confidence":0.7}'

        def batch(self, prompts, **_):
            return [self.invoke(p) for _ in prompts]

    chain = build_sec_runnable(prompt=FakePrompt(), llm=FakeLLM(), require_json=True)
    out = chain.invoke(
        {"symbol": "AAPL", "chunk": "Revenue...", "search_term": "revenue"}
    )
    assert out["status"] == "ok"
    assert out["summary"]["summary"] == "ok"
