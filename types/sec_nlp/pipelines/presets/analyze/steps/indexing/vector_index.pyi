from _typeshed import Incomplete
from langchain_core.documents import Document as Document
from langchain_qdrant import QdrantVectorStore as QdrantVectorStore

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.core.text.deduplication import (
    SimHashDeduplicator as SimHashDeduplicator,
)
from sec_nlp.pipelines.vector.query import scroll_exists as scroll_exists

from ...config import AnalyzeConfig as AnalyzeConfig
from ...types import Timings as Timings

class VectorIndexer:
    config: Incomplete
    vector_store: Incomplete
    deduplicator: Incomplete
    def __init__(
        self,
        *,
        config: AnalyzeConfig,
        vector_store: QdrantVectorStore | None,
        deduplicator: SimHashDeduplicator,
    ) -> None: ...
    def index(
        self, symbol: str, docs: list[Document], timings: Timings
    ) -> int: ...
