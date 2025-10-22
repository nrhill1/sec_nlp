from collections.abc import Callable as Callable
from collections.abc import Generator
from pathlib import Path
from typing import Any, Protocol

import pytest
from _typeshed import Incomplete
from sec_nlp.core.llm.base import LocalLLMBase as LocalLLMBase

class HasPageContent(Protocol):
    page_content: str

def _block_network() -> Generator[None, None, None]: ...
def sandbox_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]: ...
@pytest.fixture
def tmp_dirs(tmp_path: Path) -> tuple[Path, Path]: ...
@pytest.fixture
def make_fake_doc() -> Callable[[str], HasPageContent]: ...
@pytest.fixture
def write_html_tree(tmp_dirs: tuple[Path, Path]) -> Callable[..., Path]: ...

class DummyLLM(LocalLLMBase):
    _model: Incomplete
    _tokenizer: Incomplete
    def _load_backend(self) -> None: ...
    def _generate(self, prompt: str, gen_kwargs: dict[str, Any]) -> str: ...
    def force_init(self) -> None: ...

@pytest.fixture
def dummy_llm() -> Callable[[bool], DummyLLM]: ...
