# src/sec_nlp/core/text/keyword.py
"""Keyword ranking helper using pure Python (pyahocorasick if available)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping

import ahocorasick  # type: ignore[import]
from langchain_core.documents import Document
from pydantic import ConfigDict, Field, ValidationInfo, field_validator
from pydantic.dataclasses import dataclass


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class KeywordSpec:
    pattern: str
    priority: int
    weight: float


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class KeywordHit:
    pattern: str
    priority: int
    weight: float
    count: int


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class KeywordScore:
    total_score: float
    rank_vector: list[float]
    hits: list[KeywordHit]


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class FilterStats:
    kept: int
    total: int
    keyword_hits: int
    fallback_kept: int
    skipped_short: int
    skipped_dupe: int
    capped: int


type KeywordCategories = dict[str, list[str]]


@dataclass(
    frozen=True,
    config=ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
        validate_default=True,
    ),
)
class KeywordMatcher:
    """Reusable Aho-Corasick matcher for fast keyword counting."""

    KeywordCategories = KeywordCategories

    patterns: list[str]
    case_insensitive: bool = True
    automaton: ahocorasick.Automaton = Field(
        default_factory=ahocorasick.Automaton,
        description="Internal Aho-Corasick automaton",
        repr=False,
    )

    @field_validator("patterns", mode="before")
    @classmethod
    def _validate_patterns(
        cls,
        value: KeywordMatcher | Iterable[str],
    ) -> list[str]:
        if isinstance(value, KeywordMatcher):
            patterns_iterable = value.patterns
        else:
            patterns_iterable = value

        if patterns_iterable is None:
            raise TypeError("patterns is required")
        if isinstance(patterns_iterable, str):
            raise TypeError("patterns must be an iterable of strings")
        if isinstance(patterns_iterable, Mapping):
            raise TypeError("patterns must be an iterable of strings")
        if not isinstance(patterns_iterable, Iterable):
            raise TypeError("patterns must be an iterable of strings")

        cleaned: list[str] = []
        for pattern in patterns_iterable:
            if not isinstance(pattern, str):
                raise TypeError("patterns must be an iterable of strings")
            stripped = pattern.strip()
            if stripped:
                cleaned.append(stripped)

        if not cleaned:
            raise TypeError("patterns must include at least one string")

        return cleaned

    @field_validator("case_insensitive", mode="before")
    @classmethod
    def _validate_case_insensitive(cls, value: bool) -> bool:
        if not isinstance(value, bool):
            raise TypeError("case_insensitive must be a bool")
        return value

    @field_validator("automaton", mode="after")
    @classmethod
    def _build_automaton(
        cls,
        automaton: ahocorasick.Automaton,
        info: ValidationInfo,
    ) -> ahocorasick.Automaton:
        patterns = info.data.get("patterns")
        if not isinstance(patterns, list):
            raise TypeError("patterns must be a list of strings")
        case_insensitive = info.data.get("case_insensitive")
        if not isinstance(case_insensitive, bool):
            raise TypeError("case_insensitive must be a bool")

        cls._populate_automaton(
            automaton,
            patterns=patterns,
            case_insensitive=case_insensitive,
        )
        cls._validate_automaton(
            automaton,
            expected_count=len(patterns),
        )
        return automaton

    def count(self, text: str) -> tuple[dict[str, int], int]:
        if not text or not self.patterns:
            return {}, 0
        haystack = text.lower() if self.case_insensitive else text
        counts: dict[str, int] = {}
        for _, idx in self.automaton.iter(haystack):
            pattern = self.patterns[idx]
            counts[pattern] = counts.get(pattern, 0) + 1
        total = sum(counts.values())
        return counts, total

    @staticmethod
    def _add_word(
        automaton: ahocorasick.Automaton,
        word: str,
        value: int,
    ) -> None:
        automaton.add_word(word, value)

    @classmethod
    def _populate_automaton(
        cls,
        automaton: ahocorasick.Automaton,
        *,
        patterns: list[str],
        case_insensitive: bool,
    ) -> None:
        automaton.clear()
        seen: set[str] = set()
        for idx, pattern in enumerate(patterns):
            key = pattern.lower() if case_insensitive else pattern
            if key in seen:
                raise ValueError("patterns must be unique after normalization")
            seen.add(key)
            cls._add_word(automaton, key, idx)
        automaton.make_automaton()

    @staticmethod
    def _validate_automaton(
        automaton: ahocorasick.Automaton,
        *,
        expected_count: int,
    ) -> None:
        if len(automaton) != expected_count:
            raise ValueError("automaton entry count does not match patterns")

    @staticmethod
    def build_keyword_categories(
        keywords: Iterable[str],
        *,
        category_terms: Mapping[str, Iterable[str]],
    ) -> KeywordCategories:
        """Group keywords into caller-defined categories for prefilter checks."""
        categories: KeywordCategories = {name: [] for name in category_terms}
        for keyword in keywords:
            if not keyword:
                continue
            keyword_l = keyword.lower()
            for category, terms in category_terms.items():
                for term in terms:
                    term_l = term.lower()
                    if term_l and term_l in keyword_l:
                        categories[category].append(keyword_l)
                        break
        return categories

    @classmethod
    def _keyword_category_for_kw(
        cls,
        kw: str,
        categories: Mapping[str, list[str]],
    ) -> str:
        """Return the first category a keyword belongs to."""
        for cat, terms in categories.items():
            if kw in terms:
                return cat
        return "uncategorized"

    @classmethod
    def has_keyword_hit(
        cls,
        text: str,
        keywords: Iterable[str],
        categories: Mapping[str, list[str]],
        *,
        min_categories: int = 1,
    ) -> bool:
        """Lightweight keyword presence check before chunking."""
        text_lower = text.lower()
        category_hits = set()
        category_lookup = categories
        for kw in keywords:
            if not kw:
                continue
            kw_l = kw.lower()
            if kw_l in text_lower:
                category_hits.add(
                    cls._keyword_category_for_kw(kw_l, category_lookup)
                )
                if len(category_hits) >= min_categories:
                    return True
        return False

    @staticmethod
    def _prepare_specs(
        specs: Iterable[KeywordSpec],
        *,
        case_insensitive: bool,
    ) -> list[KeywordSpec]:
        cleaned: list[KeywordSpec] = []
        seen: set[str] = set()
        for spec in specs:
            if not isinstance(spec, KeywordSpec):
                raise TypeError("specs must be KeywordSpec items")
            pattern = spec.pattern.strip()
            if not pattern:
                continue
            key = pattern.lower() if case_insensitive else pattern
            if key in seen:
                continue
            seen.add(key)
            if pattern != spec.pattern:
                cleaned.append(
                    KeywordSpec(
                        pattern=pattern,
                        priority=spec.priority,
                        weight=spec.weight,
                    )
                )
            else:
                cleaned.append(spec)
        return cleaned

    @classmethod
    def score_keywords(
        cls,
        text: str,
        specs: Iterable[KeywordSpec],
        *,
        case_insensitive: bool = True,
    ) -> KeywordScore:
        """Score keyword hits in text using weighted keyword specs."""
        if not text:
            return KeywordScore(total_score=0.0, rank_vector=[], hits=[])

        cleaned_specs = cls._prepare_specs(
            specs, case_insensitive=case_insensitive
        )
        if not cleaned_specs:
            return KeywordScore(total_score=0.0, rank_vector=[], hits=[])

        matcher = cls(
            [spec.pattern for spec in cleaned_specs],
            case_insensitive=case_insensitive,
        )
        counts, _ = matcher.count(text)

        hits: list[KeywordHit] = []
        total_score = 0.0
        for spec in cleaned_specs:
            count = counts.get(spec.pattern, 0)
            if count <= 0:
                continue
            hits.append(
                KeywordHit(
                    pattern=spec.pattern,
                    priority=spec.priority,
                    weight=spec.weight,
                    count=count,
                )
            )
            total_score += spec.weight

        if not hits or total_score <= 0:
            return KeywordScore(total_score=0.0, rank_vector=[], hits=[])

        hits.sort(
            key=lambda hit: (hit.priority, hit.weight, hit.pattern),
            reverse=True,
        )
        rank_vector = [hit.weight / total_score for hit in hits]
        return KeywordScore(
            total_score=total_score,
            rank_vector=rank_vector,
            hits=hits,
        )

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
    ) -> tuple[list[Document], FilterStats]:
        """Filter documents by keyword hits, length, and dedupe with fallback."""
        if not docs:
            return [], FilterStats(0, 0, 0, 0, 0, 0, 0)

        specs = [
            KeywordSpec(pattern=kw, priority=1, weight=1.0) for kw in keywords
        ]
        has_keyword_specs = bool(specs)

        seen_hashes: set[str] = set()
        keyword_hits: list[Document] = []
        fallback_pool: list[Document] = []
        skipped_short = 0
        skipped_dupe = 0

        for doc in docs:
            text = doc.page_content or ""
            if len(text) < min_chars:
                skipped_short += 1
                continue

            digest = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()
            if dedupe and digest in seen_hashes:
                skipped_dupe += 1
                continue
            seen_hashes.add(digest)

            if has_keyword_specs:
                score = cls.score_keywords(
                    text,
                    specs,
                    case_insensitive=True,
                )
                keyword_score = score.total_score
                if score.hits:
                    doc.metadata = {
                        **(doc.metadata or {}),
                        "keyword_hits": [hit.pattern for hit in score.hits],
                        "keyword_score": keyword_score,
                    }
                    keyword_hits.append(doc)
                else:
                    fallback_pool.append(doc)
            else:
                keyword_hits.append(doc)

        fallback_kept: list[Document] = []
        if has_keyword_specs and fallback_pool:
            fallback_pool.sort(
                key=lambda d: len(d.page_content or ""), reverse=True
            )
            if max_non_keyword_chunks is None:
                fallback_kept = fallback_pool
            elif max_non_keyword_chunks > 0:
                fallback_kept = fallback_pool[:max_non_keyword_chunks]

        def _score(doc: Document) -> tuple[float, int, int]:
            meta = doc.metadata or {}
            return (
                float(meta.get("keyword_score", 0.0)),
                len(doc.page_content or ""),
                1
                if (meta.get("section_number") or meta.get("exhibit_number"))
                else 0,
            )

        keyword_hits = sorted(keyword_hits, key=_score, reverse=True)
        filtered = keyword_hits + fallback_kept

        capped = 0
        if max_chunks and len(filtered) > max_chunks:
            capped = len(filtered) - max_chunks
            filtered = filtered[:max_chunks]

        for idx, doc in enumerate(filtered, 1):
            doc.metadata = {
                **(doc.metadata or {}),
                "rank": idx,
            }

        stats = FilterStats(
            kept=len(filtered),
            total=len(docs),
            keyword_hits=len(keyword_hits),
            fallback_kept=len(fallback_kept),
            skipped_short=skipped_short,
            skipped_dupe=skipped_dupe,
            capped=capped,
        )
        return filtered, stats
