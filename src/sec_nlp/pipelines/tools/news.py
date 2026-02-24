# src/sec_nlp/pipelines/tools/news.py
"""LangChain tool wrapper for deterministic news context retrieval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from time import monotonic

from langchain_core.tools import StructuredTool

from sec_nlp.core.news.client import create_news_retriever
from sec_nlp.core.types import as_json_dict
from sec_nlp.types import JsonDict

from .schemas import NewsContextToolInput, NewsContextToolOutput


def _check_timeout(
    *,
    started_at: float,
    timeout_seconds: float | None,
    stage: str,
) -> None:
    if timeout_seconds is None:
        return
    elapsed = monotonic() - started_at
    if elapsed > timeout_seconds:
        raise TimeoutError(
            f"news_context_tool timed out during {stage} after {elapsed:.2f}s"
        )


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(cleaned)
    except (TypeError, ValueError):
        return None


def _run_news_context_tool(
    *,
    keywords: list[str],
    max_results: int = 50,
    lookback_days: int = 14,
    timeout_seconds: float | None = 30.0,
) -> JsonDict:
    started_at = monotonic()
    cutoff_date = datetime.now(UTC).date() - timedelta(days=lookback_days)
    retriever = create_news_retriever(
        user_agent="SEC NLP Tool (tooling@local)",
        rate_limit_secs=0.15,
    )
    _check_timeout(
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        stage="news client setup",
    )
    raw_items = retriever.fetch(keywords=keywords, max_results=max_results)
    _check_timeout(
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        stage="news fetch",
    )

    deduped: list[JsonDict] = []
    seen: set[str] = set()
    for item in raw_items:
        published_at = _parse_timestamp(item.published_at)
        if published_at is None:
            continue
        published = published_at.astimezone(UTC)
        if published.date() < cutoff_date:
            continue
        dedupe_key = f"{item.title.casefold()}::{item.url.casefold()}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(
            {
                "published_at": published.isoformat(),
                "source": item.source,
                "title": item.title,
                "url": item.url,
                "matched_keywords": item.matched_keywords,
                "snippet": item.snippet,
            }
        )
    deduped.sort(
        key=lambda item: str(item.get("published_at") or ""),
        reverse=True,
    )

    output = NewsContextToolOutput(
        lookback_days=lookback_days,
        items=deduped[:max_results],
    )
    payload = as_json_dict(output.model_dump(mode="json", exclude_none=True))
    if payload is None:
        raise ValueError("news_context_tool produced a non-JSON payload")
    return payload


news_context_tool = StructuredTool.from_function(
    name="news_context_tool",
    description=(
        "Fetch and deduplicate recent news/headline context for provided keywords."
    ),
    func=_run_news_context_tool,
    args_schema=NewsContextToolInput,
)
