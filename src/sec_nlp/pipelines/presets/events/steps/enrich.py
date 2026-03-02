# src/sec_nlp/pipelines/presets/events/steps/enrich.py
"""Attach nearby news headlines to detected events."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime

from sec_nlp.core.news.client import create_news_retriever
from sec_nlp.pipelines.presets.news.steps.fetch import resolve_symbol_aliases

from ..config import EventsSettings
from ..models import DetectedEvent, EventHeadline


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse timestamp strings into timezone-aware datetimes."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None

    try:
        return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        pass

    try:
        return parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None


def _headline_dedupe_key(headline: EventHeadline) -> str:
    """Build dedupe key for normalized headline records."""
    return f"{headline.title.strip().lower()}::{headline.url.strip().lower()}"


def enrich_events_with_news(
    *,
    symbol: str,
    events: list[DetectedEvent],
    settings: EventsSettings,
) -> tuple[list[DetectedEvent], int]:
    """Enrich events with nearby headlines."""

    if not events or not settings.include_news_context:
        return events, 0

    symbol_aliases = resolve_symbol_aliases(symbol=symbol, settings=settings)
    base_keywords = [
        alias for alias in symbol_aliases if alias and not alias.startswith("$")
    ]

    retriever = create_news_retriever(
        user_agent=f"SEC NLP Tool ({settings.email})",
        rate_limit_secs=0.15,
    )

    enriched: list[DetectedEvent] = []
    linked_headlines = 0
    for event in events:
        event_date = date.fromisoformat(event.event_date)
        window_start = event_date - timedelta(days=settings.news_window_days)
        window_end = event_date + timedelta(days=settings.news_window_days)

        keywords = list(base_keywords)
        keywords.extend(part for part in event.event_type.split("_") if part)
        keywords = list(dict.fromkeys(keywords))

        raw_items = retriever.fetch(
            keywords,
            max_results=max(settings.max_headlines_per_event * 4, 20),
        )

        headlines: list[EventHeadline] = []
        seen: set[str] = set()
        for item in raw_items:
            published_dt = _parse_timestamp(item.published_at)
            if published_dt is None:
                continue
            published_utc = published_dt.astimezone(UTC)
            published_date = published_utc.date()
            if published_date < window_start or published_date > window_end:
                continue

            headline = EventHeadline(
                title=item.title.strip(),
                url=item.url,
                source=item.source,
                published_at=published_utc.isoformat(),
                published_date=published_date.isoformat(),
            )
            dedupe_key = _headline_dedupe_key(headline)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            headlines.append(headline)

        headlines.sort(
            key=lambda current: (current.published_at or "", current.title),
            reverse=True,
        )
        headlines = headlines[: settings.max_headlines_per_event]
        linked_headlines += len(headlines)

        enriched.append(
            event.model_copy(
                update={
                    "headlines": headlines,
                }
            )
        )

    return enriched, linked_headlines
