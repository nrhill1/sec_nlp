from datetime import date
from pathlib import Path
from typing import Any, Self

from _typeshed import Incomplete
from langchain_core.prompts.base import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from pydantic import BaseModel, computed_field
from qdrant_client import QdrantClient

from sec_nlp.core.config import get_logger as get_logger
from sec_nlp.core.config import settings as settings
from sec_nlp.core.downloader import FilingManager as FilingManager
from sec_nlp.core.enums import FilingMode as FilingMode
from sec_nlp.core.llm.chains import SummarizationInput as SummarizationInput
from sec_nlp.core.llm.chains import SummarizationOutput as SummarizationOutput
from sec_nlp.core.llm.chains import SummarizationResult as SummarizationResult
from sec_nlp.core.llm.chains import build_summarization_runnable as build_summarization_runnable
from sec_nlp.core.preprocessor import Preprocessor as Preprocessor

logger: Incomplete

def _get_version() -> str: ...
def _slugify(s: str) -> str: ...
def _safe_name(s: str, allow: str = "a-zA-Z0-9._-") -> str: ...
def default_prompt_path() -> Path: ...
def default_output_path() -> Path: ...
def default_download_path() -> Path: ...

class Pipeline(BaseModel):
    mode: FilingMode
    start_date: date
    end_date: date
    keyword: str
    model_name: str
    prompt_file: Path
    out_path: Path
    dl_path: Path
    limit: int | None
    max_new_tokens: int
    require_json: bool
    max_retries: int
    batch_size: int
    email: str | None
    collection_name: str | None
    dry_run: bool
    _prompt: BasePromptTemplate[Any]
    _pre: Preprocessor | None
    _qdrant: QdrantClient | None
    _embedder: Any | None
    _embedding_dim: int | None
    _graph: Runnable[SummarizationInput, SummarizationOutput] | None
    @classmethod
    def _check_start(cls, v: date) -> date: ...
    @classmethod
    def _not_too_old(cls, v: date) -> date: ...
    @classmethod
    def _nonempty_keyword(cls, v: str) -> str: ...
    @classmethod
    def _validate_prompt_file(cls, p: Path) -> Path: ...
    @classmethod
    def _ensure_dirs(cls, v: Path) -> Path: ...
    @classmethod
    def _positive_limit(cls, v: int | None) -> int | None: ...
    @classmethod
    def _positive_ints(cls, v: int) -> int: ...
    def _check_dates(self) -> Self: ...
    @computed_field
    @property
    def keyword_lower(self) -> str: ...
    def _collection_slug(self, symbol: str) -> str: ...
    def model_post_init(self, /, __ctx: Any) -> None: ...
    def _get_preprocessor(self) -> Preprocessor: ...
    def _ensure_qdrant(self) -> QdrantClient: ...
    def _ensure_embedder(self) -> Any: ...
    def _ensure_collection(self, collection_name: str) -> None: ...
    def _embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def _upsert_texts(
        self,
        collection_name: str,
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]: ...
    def _get_graph(self) -> Runnable[SummarizationInput, SummarizationOutput]: ...
    def run_all(self, symbols: list[str]) -> dict[str, list[Path]]: ...
    def run(self, symbol: str) -> list[Path]: ...
