from pathlib import Path
from typing import Any, ClassVar

from _typeshed import Incomplete
from langchain_core.language_models import (
    BaseLanguageModel as BaseLanguageModel,
)
from langchain_core.prompts.base import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from pydantic import BaseModel
from qdrant_client import QdrantClient

from sec_nlp.core import FilingManager as FilingManager
from sec_nlp.core import Preprocessor as Preprocessor
from sec_nlp.core import get_logger as get_logger
from sec_nlp.core.llm.chains import build_runnable as build_runnable
from sec_nlp.pipelines.base import BasePipeline as BasePipeline
from sec_nlp.pipelines.base import BaseResult as BaseResult
from sec_nlp.pipelines.registry import PipelineRegistry as PipelineRegistry
from sec_nlp.pipelines.summary.config import SummaryConfig as SummaryConfig

logger: Incomplete

def _slugify(s: str) -> str: ...
def _safe_name(s: str, allow: str = "a-zA-Z0-9._-") -> str: ...

class SummaryInput(BaseModel):
    chunk: str
    symbol: str
    search_term: str

class SummaryResult(BaseResult):
    pipeline_type: ClassVar[str]
    summary: str | None
    points: list[str] | None
    confidence: float | None

class SummaryPipeline(BasePipeline[SummaryConfig, SummaryInput, SummaryResult]):
    pipeline_type: ClassVar[str]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    requires_vector_db: ClassVar[bool]
    _prompt: BasePromptTemplate[Any]
    _llm: BaseLanguageModel[Any]
    _graph: Runnable[SummaryInput, SummaryResult] | None
    _pre: Preprocessor | None
    _qdrant: QdrantClient | None
    _embedder: Any | None
    _embedding_dim: int | None
    def _model_post_init_() -> None: ...
    def _build_components(self) -> None: ...
    def validate_inputs(self, input_data: SummaryInput) -> None: ...
    def _validate_config(self) -> None: ...
    def run(self, symbols: list[str]) -> SummaryResult: ...
    def _process_symbol(self, symbol: str) -> list[Path]: ...
    def _get_preprocessor(self) -> Preprocessor: ...
    def _get_graph(self) -> Runnable[SummaryInput, SummaryResult]: ...
    def _collection_slug(self, symbol: str) -> str: ...
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
    def _cleanup_downloads(self) -> None: ...
