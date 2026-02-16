"""Topic relevance scoring for fetched headlines."""

from __future__ import annotations

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.ranking import score_document

from ..models import NewsHeadline


def _normalize_topics(topics: list[str]) -> list[str]:
    normalized: list[str] = []
    for topic in topics:
        cleaned = topic.strip()
        if cleaned:
            normalized.append(cleaned)
    return list(dict.fromkeys(normalized))


def _simple_score(text: str, topics: list[str]) -> tuple[list[str], float]:
    if not topics:
        return [], 1.0

    lowered = text.lower()
    matched: list[str] = []
    for topic in topics:
        candidate = topic.lower().strip()
        if candidate and candidate in lowered:
            matched.append(topic)

    score = len(matched) / len(topics)
    return matched, score


def _efts_score(text: str, topics: list[str]) -> tuple[list[str], float]:
    topic_score = score_document(text, topics, case_insensitive=True)
    matched = [
        topic
        for topic, hit_count in topic_score.keyword_counts.items()
        if hit_count > 0
    ]
    if not topics:
        return matched, 1.0

    # Keep this on a predictable [0, 1] scale for thresholding.
    score = len(matched) / len(topics)
    return matched, score


def match_news_items(
    *,
    items: list[NewsHeadline],
    topics: list[str],
    min_relevance: float,
) -> list[NewsHeadline]:
    """Score and filter headlines by topic relevance."""

    if not items:
        return []

    normalized_topics = _normalize_topics(topics)
    if not normalized_topics:
        passthrough: list[NewsHeadline] = []
        for item in items:
            passthrough.append(
                item.model_copy(
                    update={
                        "matched_topics": list(item.matched_keywords),
                        "relevance_score": 1.0,
                    }
                )
            )
        return passthrough

    use_efts = True
    scored: list[NewsHeadline] = []

    for item in items:
        text = " ".join(
            part for part in (item.title, item.snippet or "") if part
        )
        if use_efts:
            try:
                matched_topics, relevance = _efts_score(text, normalized_topics)
            except Exception:
                use_efts = False
                logger.debug(
                    "EFTS topic scoring unavailable; falling back to substring scoring"
                )
                matched_topics, relevance = _simple_score(
                    text, normalized_topics
                )
        else:
            matched_topics, relevance = _simple_score(text, normalized_topics)

        if relevance < min_relevance:
            continue

        combined_topics = list(
            dict.fromkeys(list(item.matched_keywords) + matched_topics)
        )
        scored.append(
            item.model_copy(
                update={
                    "matched_topics": combined_topics,
                    "relevance_score": relevance,
                }
            )
        )

    scored.sort(
        key=lambda current: (
            current.relevance_score,
            current.published_at or "",
            current.title.lower(),
        ),
        reverse=True,
    )
    return scored
