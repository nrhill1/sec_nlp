from collections.abc import Callable as Callable
from collections.abc import Generator
from pathlib import Path
from typing import Protocol

import pytest

from sec_nlp.core.llm.base import LocalLLMBase as LocalLLMBase

class HasPageContent(Protocol):
    page_content: str

def sandbox_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]: ...
@pytest.fixture
def tmp_dirs(tmp_path: Path) -> tuple[Path, Path]: ...
@pytest.fixture
def make_fake_doc() -> Callable[[str], HasPageContent]: ...
@pytest.fixture
def write_html_tree(tmp_dirs: tuple[Path, Path]) -> Callable[..., Path]: ...

class DummyLLM(LocalLLMBase):
    def force_init(self) -> None: ...

@pytest.fixture
def dummy_llm() -> Callable[[bool], DummyLLM]: ...
