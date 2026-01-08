from collections.abc import Iterable, Mapping

import ahocorasick
from langchain_core.documents import Document as Document
from pydantic import ValidationInfo as ValidationInfo

class KeywordSpec:
    pattern: str
    priority: int
    weight: float

class KeywordHit:
    pattern: str
    priority: int
    weight: float
    count: int

class KeywordScore:
    total_score: float
    rank_vector: list[float]
    hits: list[KeywordHit]

class FilterStats:
    kept: int
    total: int
    keyword_hits: int
    fallback_kept: int
    skipped_short: int
    skipped_dupe: int
    capped: int

type KeywordCategories = dict[str, list[str]]

class KeywordMatcher:
    KeywordCategories = KeywordCategories
    patterns: list[str]
    case_insensitive: bool
    automaton: ahocorasick.Automaton
    def count(self, text: str) -> tuple[dict[str, int], int]: ...
    @staticmethod
    def build_keyword_categories(
        keywords: Iterable[str], *, category_terms: Mapping[str, Iterable[str]]
    ) -> KeywordCategories: ...
    @classmethod
    def has_keyword_hit(
        cls,
        text: str,
        keywords: Iterable[str],
        categories: Mapping[str, list[str]],
        *,
        min_categories: int = 1,
    ) -> bool: ...
    @classmethod
    def score_keywords(
        cls,
        text: str,
        specs: Iterable[KeywordSpec],
        *,
        case_insensitive: bool = True,
    ) -> KeywordScore: ...
    @classmethod
    def filter_docs_by_keywords(
        cls,
        docs: list[Document],
        keywords: list[str],
        *,
        min_chars: int,
        dedupe: bool = True,
        max_non_keyword_chunks: int | None = None,
        max_chunks: int | None = None,
    ) -> tuple[list[Document], FilterStats]: ...
