from collections.abc import Sequence
from pathlib import Path

from _typeshed import Incomplete
from langchain_core.documents import Document

from sec_nlp.core.infra.settings import PROJECT_ROOT as PROJECT_ROOT

env_nltk: str | None
NLTK_DATA_DIR: Path
nltk_data_dir: Incomplete

def count_sentences(text: str) -> int: ...

class SentenceSplitter:
    def __init__(
        self, *, chunk_size: int = 10, chunk_overlap: int = 2
    ) -> None: ...
    @property
    def max_sentences(self) -> int: ...
    @property
    def overlap_sentences(self) -> int: ...
    def split_text(self, text: str) -> list[str]: ...
    def split_text_with_counts(self, text: str) -> list[tuple[str, int]]: ...
    def split_documents(self, docs: Sequence[Document]) -> list[Document]: ...
