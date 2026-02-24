# tests/core/test_keyword.py
"""Tests for keyword helpers."""

from __future__ import annotations

from sec_nlp.core.text.keyword import KeywordMatcher, KeywordSpec


def test_keyword_ranker_basic() -> None:
    specs = [
        KeywordSpec(pattern="alpha", priority=10, weight=2.0),
        KeywordSpec(pattern="beta", priority=5, weight=1.0),
    ]

    res = KeywordMatcher.score_keywords(
        "Alpha beta beta", specs, case_insensitive=True
    )

    assert res.total_score == 3.0
    assert res.rank_vector == [2.0 / 3.0, 1.0 / 3.0]
    assert len(res.hits) == 2
    assert res.hits[0].pattern == "alpha"
    assert res.hits[0].count == 1
    assert res.hits[1].pattern == "beta"
    assert res.hits[1].count == 2
