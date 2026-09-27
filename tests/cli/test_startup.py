# tests/cli/test_startup.py
"""Fresh-process import and side-effect checks for help, version, and cached startup."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("arguments", [["--help"], ["--version"], []])
@pytest.mark.parametrize("terminal", [False, True])
def test_bootstrap_avoids_optional_imports_and_workspace_writes(
    tmp_path: Path, arguments: list[str], terminal: bool
) -> None:
    """Prove default noninteractive dispatch never loads providers or creates a run."""
    code = """
import sys
from pathlib import Path
from sec_nlp.cli.__main__ import main

def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise AssertionError("Startup attempted network access")
sys.addaudithook(audit)
if sys.argv.pop(1) == "tty":
    sys.stdin.isatty = lambda: True
    sys.stdout.isatty = lambda: True
assert main(sys.argv[1:]) == 0
for forbidden in ("langchain", "qdrant", "ollama", "unstructured", "nltk", "numpy", "pandas", "textual", "httpx", "sec_nlp.app", "sec_nlp.pipelines"):
    assert not any(name.startswith(forbidden) for name in sys.modules), forbidden
"""
    environment = {
        **os.environ,
        "SEC_NLP_CACHE_DIR": str(tmp_path / "cache"),
        "SEC_NLP_DATA_DIR": str(tmp_path / "data"),
    }
    result = subprocess.run(
        [sys.executable, "-c", code, "tty" if terminal else "pipe", *arguments],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize(
    "arguments",
    [["open"], ["inbox"], ["pulse"], ["watchlist"], ["status"], ["jobs"]],
)
def test_cached_commands_return_to_shell_without_ui_or_network(
    tmp_path: Path, arguments: list[str]
) -> None:
    """Keep ordinary cached command output free of UI imports and provider access."""
    code = """
import sys
from pathlib import Path
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.cli.__main__ import main

def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise AssertionError("Cached command attempted external work")
sys.addaudithook(audit)
path = Path(sys.argv[1])
assert main(["workspace", *sys.argv[2:], "--workspace", str(path)]) == 0
assert not WorkspaceStore(path).list_jobs()
for forbidden in ("langchain", "qdrant", "ollama", "unstructured", "numpy", "pandas", "textual", "webbrowser", "sec_nlp.tui", "sec_nlp.pipelines"):
    assert not any(name == forbidden or name.startswith(forbidden + ".") for name in sys.modules), forbidden
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), *arguments],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "\x1b[?1049" not in result.stdout


def test_cached_terminal_imports_no_research_or_parser_runtime(
    tmp_path: Path,
) -> None:
    """Mount the installed terminal in a fresh process with cached state only."""
    code = """
import asyncio
import sys
from pathlib import Path
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.tui.app import ResearchWorkspace

def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise AssertionError("Cached terminal attempted network access")
sys.addaudithook(audit)
async def check():
    store = WorkspaceStore(Path(sys.argv[1]))
    app = ResearchWorkspace(store=store)
    async with app.run_test(size=(100, 35)):
        assert not store.list_jobs()
        for forbidden in ("langchain", "qdrant", "ollama", "unstructured", "nltk", "numpy", "pandas", "sec_nlp.pipelines"):
            assert not any(name.startswith(forbidden) for name in sys.modules), forbidden
asyncio.run(check())
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
