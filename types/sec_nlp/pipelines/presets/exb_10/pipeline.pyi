from typing import ClassVar, Literal, TypedDict

from _typeshed import Incomplete
from langchain_core.documents import Document as Document
from langchain_qdrant import QdrantVectorStore as QdrantVectorStore
from qdrant_client import QdrantClient as QdrantClient

from sec_nlp.core.infra.logger import (
    log_divider as log_divider,
    logger as logger,
)
from sec_nlp.core.ingest.loader import Loader as Loader
from sec_nlp.core.text.keyword import KeywordMatcher as KeywordMatcher
from sec_nlp.pipelines import BasePipeline as BasePipeline
from sec_nlp.pipelines.chunk_filters import (
    limit_docs_per_accession as limit_docs_per_accession,
)
from sec_nlp.pipelines.metadata.exhibit10 import (
    prepare_vector_docs as prepare_vector_docs,
)
from sec_nlp.pipelines.observability.telemetry import (
    log_chunk_length_stats as log_chunk_length_stats,
    log_filter_stats as log_filter_stats,
)
from sec_nlp.pipelines.output_io import write_json as write_json
from sec_nlp.pipelines.utils import slugify as slugify
from sec_nlp.pipelines.vector import upload_documents as upload_documents
from sec_nlp.pipelines.vector.query import scroll_exists as scroll_exists
from sec_nlp.types import (
    JsonValue as JsonValue,
    ResultDict as ResultDict,
)

from .config import Exhibit10Config as Exhibit10Config
from .io.outputs import write_exhibit10_outputs as write_exhibit10_outputs
from .models import Exhibit10Result as Exhibit10Result
from .steps.extract.exhibits import (
    collect_exhibit_documents as collect_exhibit_documents,
)
from .steps.search.payloads import (
    SearchManifestMetaPayload as SearchManifestMetaPayload,
    SearchManifestPayload as SearchManifestPayload,
    SearchRecordPayload as SearchRecordPayload,
)
from .steps.search.search import Exhibit10Search as Exhibit10Search

class SearchRecord(TypedDict):
    query: str
    query_slug: str
    output_file: str | None
    num_results: int
    top_symbols: list[str]

EXHIBIT10_KEYWORD_CATEGORY_TERMS: Incomplete

class Exhibit10Pipeline(BasePipeline):
    pipeline_type: ClassVar[Literal["exhibit10"]]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    requires_vector_db: ClassVar[bool]
    config: Exhibit10Config
    @classmethod
    def config_model(cls) -> type[Exhibit10Config]: ...
    @classmethod
    def result_model(cls) -> type[Exhibit10Result]: ...
    def run(self) -> Exhibit10Result: ...
