"""Correlate headline activity with filings and market moves."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from math import sqrt

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.filings import get_filing_date_from_dir
from sec_nlp.core.market import MarketExtensionError, create_market_retriever
from sec_nlp.core.stats.correlation import CorrExtensionError, pearson

from ..config import NewsSettings
from ..models import (
    FilingEvent,
    NewsCluster,
    NewsCorrelation,
    NewsHeadline,
    NewsTimelineEntry,
)

_DEFAULT_FILING_FORMS: tuple[str, ...] = ("8-K", "10-K", "10-Q")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None


def _headline_date(item: NewsHeadline) -> date | None:
    if item.published_date:
        try:
            return date.fromisoformat(item.published_date)
        except ValueError:
            pass
    parsed = _parse_iso_datetime(item.published_at)
    if parsed is not None:
        return parsed.astimezone(UTC).date()
    return None


def _effective_date_window(
    settings: NewsSettings,
    items: list[NewsHeadline],
) -> tuple[date, date]:
    dated_items = [_headline_date(item) for item in items]
    known_dates = [value for value in dated_items if value is not None]
    if known_dates:
        return min(known_dates), max(known_dates)
    return settings.effective_news_date_range


def _collect_filing_events(
    *,
    symbol: str,
    settings: NewsSettings,
    start_date: date,
    end_date: date,
) -> list[FilingEvent]:
    from sec_edgar_downloader import Downloader

    forms = settings.forms or list(_DEFAULT_FILING_FORMS)
    extended_start = start_date - timedelta(
        days=settings.filing_match_window_days
    )
    extended_end = end_date + timedelta(days=settings.filing_match_window_days)

    downloader = Downloader(
        "SEC NLP Tool", settings.email, str(settings.dl_path)
    )
    for form in forms:
        try:
            downloader.get(
                form,
                symbol,
                after=extended_start,
                before=extended_end,
                limit=max(8, settings.days // 10),
                download_details=True,
            )
        except Exception as exc:
            logger.debug(
                "Unable to refresh %s filings for %s: %s",
                form,
                symbol,
                exc,
            )

    events: list[FilingEvent] = []
    for form in forms:
        form_dir = (
            settings.dl_path / "sec-edgar-filings" / symbol.upper() / form
        )
        if not form_dir.exists():
            continue
        for accession_dir in form_dir.iterdir():
            if not accession_dir.is_dir():
                continue
            filing_date = get_filing_date_from_dir(accession_dir)
            if filing_date is None:
                continue
            if filing_date < extended_start or filing_date > extended_end:
                continue
            events.append(
                FilingEvent(
                    filing_date=filing_date.isoformat(),
                    form_type=form,
                    accession_number=accession_dir.name,
                )
            )

    deduped: dict[str, FilingEvent] = {}
    for event in sorted(
        events,
        key=lambda current: (current.filing_date, current.form_type),
        reverse=True,
    ):
        deduped[event.accession_number] = event

    return sorted(
        deduped.values(),
        key=lambda current: (current.filing_date, current.form_type),
    )


def _nearest_filing(
    *,
    item_date: date,
    filings: list[FilingEvent],
    max_window_days: int,
) -> FilingEvent | None:
    nearest: FilingEvent | None = None
    nearest_delta: int | None = None

    for filing in filings:
        filing_date = date.fromisoformat(filing.filing_date)
        delta = abs((filing_date - item_date).days)
        if nearest_delta is None or delta < nearest_delta:
            nearest_delta = delta
            nearest = filing

    if nearest is None:
        return None
    if nearest_delta is None or nearest_delta > max_window_days:
        return None
    return nearest


def _build_market_series(
    *,
    symbol: str,
    include_market_context: bool,
    start_date: date,
    end_date: date,
) -> tuple[dict[date, float], dict[date, float]]:
    if not include_market_context:
        return {}, {}

    retriever = create_market_retriever()
    query_start = start_date - timedelta(days=1)
    query_end = end_date + timedelta(days=1)

    try:
        quotes = retriever.retrieve_range(symbol, (query_start, query_end))
    except MarketExtensionError:
        logger.debug(
            "Market extension unavailable; skipping market correlation"
        )
        return {}, {}
    except Exception as exc:
        logger.debug("Unable to fetch market quotes for %s: %s", symbol, exc)
        return {}, {}

    close_by_date: dict[date, tuple[int, float]] = {}
    for quote in quotes:
        quote_date = datetime.fromtimestamp(quote.timestamp, UTC).date()
        existing = close_by_date.get(quote_date)
        if existing is None or quote.timestamp > existing[0]:
            close_by_date[quote_date] = (quote.timestamp, quote.close)

    closes = {day: payload[1] for day, payload in close_by_date.items()}

    returns: dict[date, float] = {}
    ordered_days = sorted(closes)
    previous_close: float | None = None
    for day in ordered_days:
        close = closes[day]
        if previous_close is not None and previous_close != 0:
            returns[day] = (close - previous_close) / previous_close
        previous_close = close

    return closes, returns


def _fallback_pearson(
    x_values: list[float], y_values: list[float]
) -> float | None:
    if len(x_values) < 2 or len(y_values) < 2:
        return None

    n = len(x_values)
    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n

    numerator = sum(
        (x_values[idx] - mean_x) * (y_values[idx] - mean_y) for idx in range(n)
    )
    denominator_x = sum((value - mean_x) ** 2 for value in x_values)
    denominator_y = sum((value - mean_y) ** 2 for value in y_values)
    denominator = sqrt(denominator_x * denominator_y)
    if denominator == 0:
        return None

    return numerator / denominator


def _compute_correlation(
    *,
    news_counts: dict[date, int],
    market_returns: dict[date, float],
) -> tuple[float | None, int]:
    paired_dates = sorted(set(news_counts) & set(market_returns))
    if len(paired_dates) < 2:
        return None, len(paired_dates)

    x_values = [float(news_counts[current]) for current in paired_dates]
    y_values = [market_returns[current] for current in paired_dates]

    try:
        corr_value = pearson(x_values, y_values)
    except CorrExtensionError:
        corr_value = _fallback_pearson(x_values, y_values)
    except Exception:
        corr_value = _fallback_pearson(x_values, y_values)

    return corr_value, len(paired_dates)


def _detect_clusters(
    *,
    news_counts: dict[date, int],
    threshold: int,
    gap_days: int,
) -> list[NewsCluster]:
    if not news_counts:
        return []

    clusters: list[NewsCluster] = []
    sorted_days = sorted(news_counts)

    window_start = sorted_days[0]
    previous_day = sorted_days[0]
    headline_total = news_counts[window_start]

    for current_day in sorted_days[1:]:
        day_gap = (current_day - previous_day).days
        if day_gap <= gap_days + 1:
            headline_total += news_counts[current_day]
            previous_day = current_day
            continue

        if headline_total >= threshold:
            clusters.append(
                NewsCluster(
                    start_date=window_start.isoformat(),
                    end_date=previous_day.isoformat(),
                    headline_count=headline_total,
                )
            )

        window_start = current_day
        previous_day = current_day
        headline_total = news_counts[current_day]

    if headline_total >= threshold:
        clusters.append(
            NewsCluster(
                start_date=window_start.isoformat(),
                end_date=previous_day.isoformat(),
                headline_count=headline_total,
            )
        )

    return clusters


def correlate_news_items(
    *,
    symbol: str,
    items: list[NewsHeadline],
    settings: NewsSettings,
) -> tuple[list[NewsHeadline], list[NewsTimelineEntry], NewsCorrelation]:
    """Link headlines to filings/market data and build timeline rows."""
    if not items:
        empty_corr = NewsCorrelation()
        return [], [], empty_corr

    start_date, end_date = _effective_date_window(settings, items)

    filings = _collect_filing_events(
        symbol=symbol,
        settings=settings,
        start_date=start_date,
        end_date=end_date,
    )
    market_close, market_returns = _build_market_series(
        symbol=symbol,
        include_market_context=settings.include_market_context,
        start_date=start_date,
        end_date=end_date,
    )

    annotated: list[NewsHeadline] = []
    headlines_by_date: dict[date, list[NewsHeadline]] = {}

    for item in items:
        item_date = _headline_date(item)
        nearest = (
            _nearest_filing(
                item_date=item_date,
                filings=filings,
                max_window_days=settings.filing_match_window_days,
            )
            if item_date is not None
            else None
        )

        updated = item.model_copy(
            update={
                "nearest_filing_date": nearest.filing_date if nearest else None,
                "nearest_filing_form": nearest.form_type if nearest else None,
                "nearest_filing_accession": (
                    nearest.accession_number if nearest else None
                ),
                "market_close": (
                    market_close.get(item_date)
                    if item_date is not None
                    else None
                ),
                "market_return": (
                    market_returns.get(item_date)
                    if item_date is not None
                    else None
                ),
            }
        )
        annotated.append(updated)

        if item_date is not None:
            headlines_by_date.setdefault(item_date, []).append(updated)

    news_counts = {
        current_date: len(headlines)
        for current_date, headlines in headlines_by_date.items()
    }

    corr_value, days_compared = _compute_correlation(
        news_counts=news_counts,
        market_returns=market_returns,
    )
    clusters = _detect_clusters(
        news_counts=news_counts,
        threshold=settings.cluster_threshold,
        gap_days=settings.cluster_gap_days,
    )

    filings_by_date: dict[str, list[FilingEvent]] = {}
    for filing in filings:
        filings_by_date.setdefault(filing.filing_date, []).append(filing)

    all_dates = sorted(
        {date_key.isoformat() for date_key in headlines_by_date}
        | set(filings_by_date),
        reverse=True,
    )

    timeline: list[NewsTimelineEntry] = []
    for day_text in all_dates:
        day = date.fromisoformat(day_text)
        day_headlines = list(headlines_by_date.get(day, []))
        day_headlines.sort(
            key=lambda current: (
                current.relevance_score,
                current.published_at or "",
            ),
            reverse=True,
        )

        timeline.append(
            NewsTimelineEntry(
                date=day_text,
                headline_count=len(day_headlines),
                headlines=day_headlines,
                filings=filings_by_date.get(day_text, []),
                market_close=market_close.get(day),
                market_return=market_returns.get(day),
            )
        )

    days_with_news = len(news_counts)
    average_daily_headlines = (
        sum(news_counts.values()) / days_with_news if days_with_news else 0.0
    )

    filings_linked = sum(
        1 for item in annotated if item.nearest_filing_accession is not None
    )

    correlation = NewsCorrelation(
        news_to_return_correlation=corr_value,
        days_compared=days_compared,
        days_with_news=days_with_news,
        days_with_market_data=len(market_returns),
        average_daily_headlines=average_daily_headlines,
        filings_linked=filings_linked,
        clusters=clusters,
    )

    return annotated, timeline, correlation
