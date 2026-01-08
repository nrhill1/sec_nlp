from collections.abc import Iterable

from _typeshed import Incomplete
from langchain_core.documents import Document as Document

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.core.text.chunking import SentenceSplitter as SentenceSplitter
from sec_nlp.core.text.deduplication import (
    SimHashConfig as SimHashConfig,
    SimHashDeduplicator as SimHashDeduplicator,
)
from sec_nlp.core.text.keyword import KeywordMatcher as KeywordMatcher
from sec_nlp.core.text.section_extractor import (
    SectionExtractor as SectionExtractor,
)
from sec_nlp.pipelines.chunk_filters import (
    limit_docs_per_accession as limit_docs_per_accession,
)

from ...config import AnalyzeConfig as AnalyzeConfig
from .topic_scoring import (
    build_topic_matcher as build_topic_matcher,
    normalize_topics as normalize_topics,
    score_documents as score_documents,
)

class ChunkPreprocessor:
    config: Incomplete
    section_extractor: Incomplete
    topics: Incomplete
    topic_matcher: Incomplete
    min_topic_hits: Incomplete
    prioritize_topics: Incomplete
    def __init__(
        self,
        *,
        config: AnalyzeConfig,
        section_extractor: SectionExtractor | None = None,
        topics: Iterable[str] | None = None,
        topic_matcher: KeywordMatcher | None = None,
        min_topic_hits: int = 0,
        prioritize_topics: bool = True,
    ) -> None: ...
    def chunk_and_prepare(self, docs: list[Document]) -> list[Document]: ...
    def split_into_chunks(self, docs: list[Document]) -> list[Document]: ...
    def prepare_documents(self, docs: list[Document]) -> list[Document]: ...
