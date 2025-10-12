from sec_nlp.chains.sec_runnable import build_sec_runnable, SummaryPayload


def test_summarypayload_ok_and_bad():
    ok = SummaryPayload.validate_from_json('{"summary":"hi","points":["a"],"confidence":0.5}')
    assert ok.error is None and ok.summary == "hi" and ok.points == ["a"]
    bad = SummaryPayload.validate_from_json("not json")
    assert bad.error is not None and bad.raw_output == "not json"


def test_chain_invoke_json_mode():
    class FakePrompt:
        def __or__(self, other): return other
        def __ror__(self, other): return self

    class FakeLLM:
        def __or__(self, other): return other
        def __ror__(self, other): return self

        def invoke(self, prompt, **_):  # returns valid JSON string
            return '{"summary":"ok","points":["x"],"confidence":0.7}'

        def batch(self, prompts, **_):
            return [self.invoke(p) for _ in prompts]
    chain = build_sec_runnable(prompt=FakePrompt(), llm=FakeLLM(), require_json=True)
    out = chain.invoke({"symbol": "AAPL", "chunk": "Revenue...", "search_term": "revenue"})
    assert out["status"] == "ok"
    assert out["summary"]["summary"] == "ok"
