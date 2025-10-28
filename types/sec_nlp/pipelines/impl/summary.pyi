from datetime import date
from pathlib import Path
from typing import Any, Literal

from _typeshed import Incomplete
from langchain_core.language_models import BaseLanguageModel as BaseLanguageModel
from langchain_core.prompts.base import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from qdrant_client import QdrantClient

from sec_nlp.core import FilingManager as FilingManager
from sec_nlp.core import FilingMode as FilingMode
from sec_nlp.core import Preprocessor as Preprocessor
from sec_nlp.core import get_logger as get_logger
from sec_nlp.core import settings as settings
from sec_nlp.core.llm.chains import SummarizationInput as SummarizationInput
from sec_nlp.core.llm.chains import SummarizationOutput as SummarizationOutput
from sec_nlp.core.llm.chains import build_summarization_runnable as build_summarization_runnable
from sec_nlp.pipelines.base import BaseConfig as BaseConfig
from sec_nlp.pipelines.base import BasePipeline as BasePipeline
from sec_nlp.pipelines.base import BaseResult as BaseResult
from sec_nlp.pipelines.registry import PipelineRegistry as PipelineRegistry

logger: Incomplete

def _slugify(s: str) -> str: ...
def _safe_name(s: str, allow: str = "a-zA-Z0-9._-") -> str: ...

class SummaryConfig(BaseConfig):
    model_config: Incomplete
    pipeline_type: Literal["summary"]
    symbols: list[str]
    mode: FilingMode
    start_date: date | None
    end_date: date | None
    keyword: str
    model_name: str
    prompt_file: Path | None
    max_new_tokens: int
    require_json: bool
    limit: int | None
    batch_size: int
    max_retries: int
    fresh: bool
    cleanup: bool
    @classmethod
    def normalize_symbols(cls, v: list[str] | str) -> list[str]: ...
    @classmethod
    def validate_keyword(cls, v: str) -> str: ...
    @classmethod
    def parse_date(cls, v: str | date | None) -> date | None: ...
    def validate_date_range(self) -> None: ...
    @classmethod
    def validate_prompt_file(cls, v: Path | None) -> Path | None: ...
    def validate_config(self) -> None: ...
    def get_date_range(self) -> tuple[date, date]: ...
    def get_prompt_path(self) -> Path | None: ...
    def to_pipeline_kwargs(self) -> dict[str, Any]: ...

class SummaryResult(BaseResult): ...

class SummaryPipeline(BasePipeline[SummaryConfig, SummaryResult]):
    description: str
    requires_model: bool
    requires_vector_db: bool
    out_path: Path
    dl_path: Path
    _prompt: BasePromptTemplate[Any]
    _llm: BaseLanguageModel[Any]
    _pre: Preprocessor | None
    _qdrant: QdrantClient | None
    _embedder: Any | None
    _embedding_dim: int | None
    _graph: Runnable[SummarizationInput, SummarizationOutput] | None
    def __init__(
        self, config: SummaryConfig, out_path: Path | None = None, dl_path: Path | None = None
    ) -> None: ...
    def validate_inputs(self) -> None: ...
    def run(self, **kwargs: Any) -> SummaryResult: ...
    def _process_symbol(self, symbol: str) -> list[Path]: ...
    def _get_preprocessor(self) -> Preprocessor: ...
    def _get_graph(self) -> Runnable[SummarizationInput, SummarizationOutput]: ...
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
