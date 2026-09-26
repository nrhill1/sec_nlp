# crates/efts/efts.pyi
"""Manual stub for the `efts` native extension."""

from __future__ import annotations

from collections.abc import Sequence

def parse_response_json(content: str, query: str) -> str:
    """Parse downloaded EFTS JSON without making network requests."""

def score_document_keywords(
    text: str,
    keywords: Sequence[str],
    case_insensitive: bool = ...,
) -> tuple[int, dict[str, int]]: ...
def rank_documents_by_keywords(
    documents: Sequence[str],
    keywords: Sequence[str],
    case_insensitive: bool = ...,
    min_hits: int = ...,
) -> list[DocumentScore]: ...

# Keyword extraction result
class KeywordResult:
    @property
    def keyword(self) -> str: ...
    @property
    def score(self) -> float: ...

# Document ranking result
class DocumentScore:
    @property
    def index(self) -> int: ...
    @property
    def score(self) -> float: ...

# YAKE keyword extractor
class YakeExtractor:
    def __init__(
        self,
        ngram_size: int = ...,
        threshold: float = ...,
        window_size: int = ...,
    ) -> None: ...
    def extract_keywords(
        self, text: str, top_n: int = ...
    ) -> list[KeywordResult]: ...

# RAKE keyword extractor
class RakeExtractor:
    def __init__(self) -> None: ...
    def extract_keywords(
        self, text: str, top_n: int = ...
    ) -> list[KeywordResult]: ...

# TextRank keyword extractor
class TextRankExtractor:
    def __init__(
        self,
        window_size: int = ...,
        damping: float = ...,
        tolerance: float = ...,
        phrase_length: int | None = ...,
    ) -> None: ...
    def extract_keywords(
        self, text: str, top_n: int = ...
    ) -> list[KeywordResult]: ...

# TF-IDF document ranker
class TfIdfRanker:
    def __init__(self) -> None: ...
    def add_documents(self, documents: Sequence[str]) -> None: ...
    def clear(self) -> None: ...
    def document_count(self) -> int: ...
    def extract_keywords(self, top_n: int = ...) -> list[KeywordResult]: ...
    def rank_by_query(
        self, query_terms: Sequence[str], top_n: int = ...
    ) -> list[DocumentScore]: ...
