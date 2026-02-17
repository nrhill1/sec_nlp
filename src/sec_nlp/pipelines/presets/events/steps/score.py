"""Compute market-impact metrics for detected events."""

from __future__ import annotations

from sec_nlp.core.stats.event_study import run_event_study

from ..config import EventsSettings
from ..models import DetectedEvent, EventImpact


def score_event_impacts(
    *,
    symbol: str,
    events: list[DetectedEvent],
    settings: EventsSettings,
) -> tuple[list[DetectedEvent], int]:
    """Attach event-study metrics to events."""

    if not events or not settings.include_market_context:
        return events, 0

    scored: list[DetectedEvent] = []
    scored_count = 0
    for event in events:
        study_5 = None
        study_30 = None

        try:
            study_5 = run_event_study(
                symbol=symbol,
                event_date=event.event_date,
                benchmark=settings.benchmark_symbol,
                pre_window=settings.pre_window_days,
                post_window=5,
            )
        except Exception:
            study_5 = None

        try:
            study_30 = run_event_study(
                symbol=symbol,
                event_date=event.event_date,
                benchmark=settings.benchmark_symbol,
                pre_window=settings.pre_window_days,
                post_window=max(settings.post_window_days, 30),
            )
        except Exception:
            study_30 = None

        impact: EventImpact | None = None
        if study_5 is not None or study_30 is not None:
            p_value = (
                study_30.p_value
                if study_30 is not None
                else study_5.p_value
                if study_5 is not None
                else None
            )
            impact = EventImpact(
                car_5d=study_5.car_post if study_5 is not None else None,
                car_30d=study_30.car_post if study_30 is not None else None,
                volume_spike=(
                    study_30.volume_spike
                    if study_30 is not None
                    else study_5.volume_spike
                    if study_5 is not None
                    else None
                ),
                t_stat=(
                    study_30.t_stat
                    if study_30 is not None
                    else study_5.t_stat
                    if study_5 is not None
                    else None
                ),
                p_value=p_value,
                significant=bool(
                    p_value is not None
                    and p_value <= settings.significance_threshold
                ),
            )
            scored_count += 1

        scored.append(event.model_copy(update={"impact": impact}))

    return scored, scored_count
