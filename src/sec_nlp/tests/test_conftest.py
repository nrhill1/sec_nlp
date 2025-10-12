# src/sec_nlp/tests/conftest.py
import os
from pathlib import Path
import pytest


@pytest.fixture(autouse=True, scope="session")
def _block_network():
    """Block real network calls during tests."""
    import socket
    orig = socket.socket

    class GuardedSocket(orig):
        def connect(self, *args, **kwargs):
            raise RuntimeError("Network access blocked during tests")

    socket.socket = GuardedSocket
    try:
        yield
    finally:
        socket.socket = orig


@pytest.fixture(autouse=True)
def sandbox_env(tmp_path, monkeypatch):
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
def tmp_dirs(tmp_path):
    """Standardized output/download dirs under tmp_path."""
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    dl = tmp_path / "dl"
    dl.mkdir(parents=True, exist_ok=True)
    return out, dl


@pytest.fixture
def make_fake_doc():
    class D:
        def __init__(self, text): self.page_content = text
    return lambda t: D(t)


@pytest.fixture
def write_html_tree(tmp_dirs):
    """
    Create a realistic SEC-EDGAR folder tree in the tmp downloads dir.
    Everything lands under pytest tmp, so it’s auto-cleaned.
    """
    _, dl = tmp_dirs

    def _mk(symbol="AAPL", form="10-K", acc="0001", fname="primary-document.html", html="<html>Revenue</html>"):
        p = dl / "sec-edgar-filings" / symbol / form / acc
        p.mkdir(parents=True, exist_ok=True)
        f = p / fname
        f.write_text(html, encoding="utf-8")
        return f
    return _mk
