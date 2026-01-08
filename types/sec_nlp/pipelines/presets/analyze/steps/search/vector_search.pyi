from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _typeshed import Incomplete
from langchain_core.documents import Document
from langchain_core.runnables import (
    RunnableConfig as RunnableConfig,
    RunnableSerializable,
)
from langchain_qdrant import QdrantVectorStore as QdrantVectorStore
from pydantic import BaseModel

from sec_nlp.core.infra.logger import (
    log_divider as log_divider,
    logger as logger,
)
from sec_nlp.pipelines.metadata.filters import (
    MetadataFilters as MetadataFilters,
    build_metadata_filter as build_metadata_filter,
)
from sec_nlp.pipelines.output_io import write_yaml as write_yaml
from sec_nlp.pipelines.types import (
    MetadataMap as MetadataMap,
    MetadataValue as MetadataValue,
)
from sec_nlp.types import (
    JsonDict as JsonDict,
    JsonValue as JsonValue,
)

from ...config import AnalyzeConfig as AnalyzeConfig
from ...utils import (
    query_term_overlap as query_term_overlap,
    resolve_symbol_for_output as resolve_symbol_for_output,
)
from ..analysis.analysis_runner import AnalysisBatchInput as AnalysisBatchInput
from .payloads import (
    SearchHighlightsPayload as SearchHighlightsPayload,
    SearchMatchPayload as SearchMatchPayload,
    SearchQuerySectionPayload as SearchQuerySectionPayload,
    SearchResultPayload as SearchResultPayload,
    SearchStatsPayload as SearchStatsPayload,
    SearchSummaryPayload as SearchSummaryPayload,
    SearchUniqueResultPayload as SearchUniqueResultPayload,
)

@dataclass(frozen=True)
class SearchQueryResults:
    filtered: list[tuple[Document, float]]
    total: int

type SearchResultsByQuery = dict[str, SearchQueryResults]

@dataclass
class _UniqueHit:
    doc: Document
    matches: dict[str, float]

class SearchRetrieveInput(BaseModel):
    model_config: Incomplete
    symbol: str | None
    queries: list[str] | None

class SearchRunnable(
    RunnableSerializable[SearchRetrieveInput, AnalysisBatchInput]
):
    model_config: Incomplete
    config: AnalyzeConfig
    vector_store: QdrantVectorStore | None
    def invoke(
        self,
        input: SearchRetrieveInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AnalysisBatchInput: ...
    def search_queries(
        self, queries: list[str] | None = None
    ) -> SearchResultsByQuery: ...
    def retrieve_hits(
        self, queries: list[str] | None = None
    ) -> list[Document]: ...
    def retrieve_hits_with_results(
        self, queries: list[str] | None = None
    ) -> tuple[list[Document], SearchResultsByQuery]: ...
    def run(self, queries: list[str] | None = None) -> list[Path]: ...
    def export_results(
        self,
        results_by_query: SearchResultsByQuery,
        *,
        cached: bool = False,
        queries: list[str] | None = None,
    ) -> list[Path]: ...
