from collections.abc import Iterable

from langchain_core.documents import Document as Document

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.core.text.keyword import KeywordMatcher as KeywordMatcher

def normalize_topics(topics: Iterable[str] | None) -> list[str]: ...
def build_topic_matcher(
    topics: Iterable[str] | None,
) -> KeywordMatcher | None: ...
def count_topics(
    content: str | None, *, topics: list[str], matcher: KeywordMatcher | None
) -> tuple[dict[str, int], int]: ...
def score_documents(
    docs: list[Document],
    *,
    topics: Iterable[str] | None,
    matcher: KeywordMatcher | None = None,
    min_hits: int = 0,
    prioritize: bool = True,
) -> list[Document]: ...
