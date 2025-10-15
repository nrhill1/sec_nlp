# sec_nlp/tests/test_llms_local_passthrough.py
from sec_nlp.llms.local_llm_base import LocalLLM


class Dummy(LocalLLM):
    def _load_backend(self):
        self._model = None

    def _generate(self, prompt, gen_kwargs):
        return "never"


def test_local_llm_passthrough_when_uninitialized(monkeypatch):
    monkeypatch.setattr(
        "sec_nlp.llms.local_llm_base.LocalLLM._lazy_imports",
        staticmethod(lambda: False),
    )
    d = Dummy(model_name="x")
    out = d.invoke("hello")
    assert out == "hello"
