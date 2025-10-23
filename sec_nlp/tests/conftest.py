# sec_nlp/tests/conftest.py
from __future__ import annotations

import json
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, Protocol

import pytest
from langchain_core.language_models import LLM
from langchain_core.runnables import Runnable, RunnableConfig


class HasPageContent(Protocol):
    page_content: str


@pytest.fixture(autouse=True, scope="session")
def _block_network() -> Generator[None, None, None]:
    """Block real network calls during tests."""
    import socket

    orig = socket.socket

    class GuardedSocket(socket.socket):  # type: ignore[misc]
        def connect(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Network access blocked during tests")

    socket.socket = GuardedSocket  # type: ignore[assignment]

    try:
        yield
    finally:
        socket.socket = orig  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def sandbox_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """
    Force *all* external caches and side effects into a temp directory,
    disable telemetry, and ensure dry/offline modes everywhere possible.
    Automatically reverts after each test.
    """
    sandbox = tmp_path / ".sandbox"
    hf = sandbox / "hf"
    xdg = sandbox / "xdg"
    pine = sandbox / "pinecone"
    for p in (hf, xdg, pine):
        p.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HF_HOME", str(hf))
    monkeypatch.setenv("TRANSFORMERS_CACHE", str(hf))
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg))
    monkeypatch.setenv("PINECONE_CACHE_DIR", str(pine))

    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "false")
    monkeypatch.setenv("NO_COLOR", "1")

    monkeypatch.setenv("PINECONE_API_KEY", "")

    monkeypatch.chdir(tmp_path)

    yield


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Standardized output/download dirs under tmp_path."""
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    dl = tmp_path / "dl"
    dl.mkdir(parents=True, exist_ok=True)
    return out, dl


@pytest.fixture
def make_fake_doc() -> Callable[[str], HasPageContent]:
    class D:
        def __init__(self, text: str) -> None:
            self.page_content = text

    def _mk(t: str) -> HasPageContent:
        return D(t)

    return _mk


@pytest.fixture
def write_html_tree(tmp_dirs: tuple[Path, Path]) -> Callable[..., Path]:
    """
    Create a realistic SEC-EDGAR folder tree in the tmp downloads dir.
    Everything lands under pytest tmp, so it’s auto-cleaned.
    """
    _, dl = tmp_dirs

    def _mk(
        symbol: str = "AAPL",
        form: str = "10-K",
        acc: str = "0001",
        fname: str = "primary-document.html",
        html: str = "<html>Revenue</html>",
    ) -> Path:
        p = dl / "sec-edgar-filings" / symbol / form / acc
        p.mkdir(parents=True, exist_ok=True)
        f = p / fname
        f.write_text(html, encoding="utf-8")
        return f

    return _mk


class DummyLLM(LLM):
    """Minimal LLM for tests.

    Default behavior keeps the backend uninitialized so that LLM.invoke
    returns the input (passthrough). Call .force_init() to simulate an initialized
    model so that invoke() uses _generate().
    """

    def _load_backend(self) -> None:
        self._model = None  # type: ignore[attr-defined]
        self._tokenizer = None  # type: ignore[attr-defined]

    def _generate(self, prompt: str, gen_kwargs: dict[str, Any]) -> str:
        return f"gen:{prompt}"

    def force_init(self) -> None:
        self._model = object()  # type: ignore[attr-defined]
        self._tokenizer = object()  # type: ignore[attr-defined]

    def invoke(self, input: str, config: RunnableConfig | None = None, **__: Any) -> str:
        return json.dumps({"summary": "ok", "points": ["x"], "confidence": 0.7})


@pytest.fixture
def dummy_llm() -> Callable[[bool], DummyLLM]:
    """Factory for DummyLLM.

    Usage in a test:
        llm = dummy_llm(initialized=False)  # passthrough (default)
        llm = dummy_llm(True)               # initialized -> uses _generate
    """

    def _make(initialized: bool = False) -> DummyLLM:
        llm = DummyLLM(model_name="dummy")
        if initialized:
            llm.force_init()
        return llm

    return _make
