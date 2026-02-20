"""Cross-filing trend analysis helpers."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from sec_nlp.pipelines.types import AnalysisResultDict
from sec_nlp.types import JsonValue

_SENTIMENT_WEIGHTS = {
    "positive": 1.0,
    "bullish": 1.0,
    "neutral": 0.0,
    "negative": -1.0,
    "bearish": -1.0,
}


class FilingTrend(BaseModel):
    """Sentiment trend across sequential filings for one symbol."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    symbol: str
    filings: list[str]
    sentiment_scores: list[float]
    trend_direction: str
    inflection_points: list[int]


def _parse_filing_date(
    raw_value: JsonValue | date | datetime,
) -> date | None:
    if isinstance(raw_value, datetime):
        return raw_value.date()
    if isinstance(raw_value, date):
        return raw_value
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if not cleaned:
            return None
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            return None
    return None


def _sentiment_score(results: list[AnalysisResultDict]) -> float | None:
    counts: Counter[str] = Counter()
    for result in results:
        sentiment = result.get("sentiment")
        if not isinstance(sentiment, str):
            continue
        cleaned = sentiment.strip().lower()
        if cleaned:
            counts[cleaned] += 1

    if not counts:
        return None

    score_sum = 0.0
    total_scored = 0
    for label, count in counts.items():
        weight = _SENTIMENT_WEIGHTS.get(label)
        if weight is None:
            continue
        score_sum += weight * count
        total_scored += count
    if total_scored <= 0:
        return None
    return score_sum / total_scored


def _trend_direction(scores: list[float]) -> str:
    if len(scores) < 2:
        return "stable"

    n = len(scores)
    x_mean = (n - 1) / 2.0
    y_mean = sum(scores) / n

    numerator = 0.0
    denominator = 0.0
    for index, score in enumerate(scores):
        dx = index - x_mean
        numerator += dx * (score - y_mean)
        denominator += dx * dx

    if denominator == 0.0:
        return "stable"
    slope = numerator / denominator

    if slope > 0.05:
        return "improving"
    if slope < -0.05:
        return "declining"
    return "stable"


def _inflection_points(scores: list[float]) -> list[int]:
    if len(scores) < 3:
        return []

    inflections: list[int] = []
    previous_sign = 0

    for index in range(1, len(scores)):
        delta = scores[index] - scores[index - 1]
        sign = 1 if delta > 0 else -1 if delta < 0 else 0
        if sign == 0:
            continue
        if previous_sign != 0 and sign != previous_sign:
            inflections.append(index)
        previous_sign = sign

    return inflections


def cross_filing_trend(
    symbol: str,
    analysis_results: list[AnalysisResultDict] | None = None,
    *,
    form_type: str = "10-K",
    periods: int = 5,
) -> FilingTrend:
    """Build a sentiment trend across filings for one symbol.

    The function consumes `analysis_results` that already include
    `source_metadata` with accession and filing date fields.
    """
    if periods <= 0:
        raise ValueError("periods must be > 0")
    if analysis_results is None:
        analysis_results = []

    filtered: list[AnalysisResultDict] = []
    target_symbol = symbol.strip().upper()
    target_form = form_type.strip().upper()

    for result in analysis_results:
        metadata = result.get("source_metadata")
        if not isinstance(metadata, dict):
            continue

        row_symbol = metadata.get("symbol")
        if (
            isinstance(row_symbol, str)
            and row_symbol.strip().upper() != target_symbol
        ):
            continue

        row_form = metadata.get("form_type")
        if (
            isinstance(row_form, str)
            and row_form.strip().upper() != target_form
        ):
            continue

        filtered.append(result)

    grouped: dict[str, list[AnalysisResultDict]] = {}
    date_by_accession: dict[str, date | None] = {}

    for result in filtered:
        metadata = result.get("source_metadata")
        if not isinstance(metadata, dict):
            continue
        accession = metadata.get("accession_number")
        if not isinstance(accession, str) or not accession.strip():
            continue
        key = accession.strip()
        grouped.setdefault(key, []).append(result)
        if key not in date_by_accession:
            date_by_accession[key] = _parse_filing_date(
                metadata.get("filing_date") or metadata.get("acceptance_date")
            )

    ordered_accessions = sorted(
        grouped,
        key=lambda accession: _accession_sort_key(
            accession,
            date_by_accession,
        ),
    )

    if periods < len(ordered_accessions):
        ordered_accessions = ordered_accessions[-periods:]

    scores: list[float] = []
    filings: list[str] = []
    for accession in ordered_accessions:
        score = _sentiment_score(grouped[accession])
        if score is None:
            continue
        filings.append(accession)
        scores.append(score)

    return FilingTrend(
        symbol=target_symbol,
        filings=filings,
        sentiment_scores=scores,
        trend_direction=_trend_direction(scores),
        inflection_points=_inflection_points(scores),
    )


def _accession_sort_key(
    accession: str,
    date_by_accession: dict[str, date | None],
) -> tuple[int, str, str]:
    filing_date = date_by_accession.get(accession)
    if filing_date is None:
        return (1, accession, accession)
    return (0, filing_date.isoformat(), accession)
