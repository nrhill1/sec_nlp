from typing import Any

from _typeshed import Incomplete
from langchain_core.callbacks.base import (
    BaseCallbackHandler as BaseCallbackHandler,
)
from langchain_core.documents import Document as Document
from langchain_core.runnables import (
    Runnable as Runnable,
    RunnableConfig,
    RunnableSerializable,
)
from pydantic import BaseModel

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.metadata.accession import (
    get_accession_from_metadata as get_accession_from_metadata,
)
from sec_nlp.pipelines.types import (
    AnalysisResultDict as AnalysisResultDict,
    MetadataRecord as MetadataRecord,
)

from ...config import AnalyzeConfig as AnalyzeConfig
from ...models import (
    AnalysisInput as AnalysisInput,
    AnalysisResult as AnalysisResult,
)
from ...utils import (
    query_term_overlap as query_term_overlap,
    resolve_symbol_for_output as resolve_symbol_for_output,
)

class AnalysisBatchInput(BaseModel):
    model_config: Incomplete
    symbol: str
    docs: list[Document]

class AnalyzerRunnable(
    RunnableSerializable[AnalysisBatchInput, list[AnalysisResultDict]]
):
    model_config: Incomplete
    config: AnalyzeConfig
    graph: Runnable[AnalysisInput, AnalysisResult]
    callbacks: list[BaseCallbackHandler]
    analysis_instructions: str
    def invoke(
        self,
        input: AnalysisBatchInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> list[AnalysisResultDict]: ...
    def analyze_chunks(
        self, symbol: str, docs: list[Document]
    ) -> list[AnalysisResultDict]: ...
    def analyze_search_hits(
        self, query: str, results: list[tuple[Document, float]]
    ) -> list[AnalysisResultDict]: ...
