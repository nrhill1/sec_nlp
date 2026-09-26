# src/sec_nlp/pipelines/presets/analyze/market.py
"""Optional market enrichment helpers for the analyze pipeline."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.market import (
    MarketExtensionError,
    MarketQuote,
    MarketRetriever,
    create_market_retriever,
)
from sec_nlp.pipelines.serialization import round_float
from sec_nlp.types import JsonDict, JsonValue


class MarketGranularity(StrEnum):
    """Supported buckets for reducing quote granularity."""

    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class MarketConfig(BaseModel):
    """Configuration for optional market enrichments."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        defer_build=True,
        str_strip_whitespace=True,
    )

    enabled: bool = Field(
        default=True,
        description="Fetch market data for the analyzed range when enabled.",
    )
    ticker: str | None = Field(
        default=None,
        description="Override the ticker used for enrichment (defaults to the target symbol).",
    )
    granularity: MarketGranularity = Field(
        default=MarketGranularity.daily,
        description="Bucket quotes into daily, weekly, or monthly averages.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        description="Maximum number of aggregated rows to include in the output.",
    )


class MarketQuoteSummary(BaseModel):
    """A single aggregated interval of market data."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    start_date: date
    end_date: date
    average_open: float
    average_high: float
    average_low: float
    average_close: float
    average_adjclose: float
    average_volume: float


class MarketEnrichment(BaseModel):
    """Market data attached to a symbol run."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        defer_build=True,
        str_strip_whitespace=True,
    )

    symbol: str
    ticker: str
    filing_date: date | None
    window_start: date
    window_end: date
    granularity: MarketGranularity
    quotes: list[MarketQuoteSummary]


def format_market_context(
    enrichment: MarketEnrichment | None,
) -> str | None:
    """Summarize market data for inclusion in the LLM context."""
    if enrichment is None or not enrichment.quotes:
        return None

    rows: list[str] = []
    for summary in enrichment.quotes[:3]:
        rows.append(
            f"{summary.start_date.isoformat()}..{summary.end_date.isoformat()} "
            f"close={summary.average_close:.2f}"
        )
    suffix = ""
    extra = len(enrichment.quotes) - len(rows)
    if extra > 0:
        suffix = f" (+{extra} more)"

    filing_hint = (
        f"filing {enrichment.filing_date.isoformat()}"
        if enrichment.filing_date
        else "filing date unknown"
    )
    window = (
        f"{enrichment.window_start.isoformat()}.."
        f"{enrichment.window_end.isoformat()}"
    )

    return (
        f"{filing_hint} | market {enrichment.ticker} "
        f"{enrichment.granularity.value} window {window}: "
        f"{'; '.join(rows)}{suffix}"
    )


_DATE_KEYS: tuple[str, ...] = (
    "filing_date",
    "acceptance_date",
    "period_end",
    "period_of_report",
    "start_date",
    "end_date",
    "document_date",
    "published_date",
)

_FILING_DATE_KEYS: tuple[str, ...] = (
    "filing_date",
    "acceptance_date",
    "period_end",
    "period_of_report",
)

_WINDOW_DELTA = timedelta(days=30)


def build_market_enrichment(
    *,
    config: MarketConfig,
    symbol: str,
    docs: Sequence[Document],
    default_range: tuple[date, date],
    retriever: MarketRetriever | None = None,
) -> MarketEnrichment | None:
    """Fetch and aggregate market data for a symbol if enabled."""

    if not config.enabled:
        return None

    ticker = config.ticker or symbol
    if not ticker:
        return None

    start_date, end_date = _derive_date_range(docs, default_range)
    filing_date = _extract_filing_date(docs)
    window_start, window_end = _extend_window(start_date, end_date)
    retriever_instance = retriever or create_market_retriever()

    try:
        raw_quotes = retriever_instance.retrieve_range(
            ticker,
            (window_start, window_end),
        )
    except MarketExtensionError as exc:
        logger.warning(
            "Market enrichment unavailable for %s (%s): %s",
            symbol,
            ticker,
            exc,
        )
        return None
    except Exception as exc:  # pragma: no cover - best effort enrichment
        logger.warning(
            "Market enrichment failed for %s (%s): %s",
            symbol,
            ticker,
            exc,
        )
        return None

    if not raw_quotes:
        logger.info(
            "Market enrichment: no quotes found for %s between %s and %s",
            ticker,
            start_date,
            end_date,
        )
        return None

    aggregated = _aggregate_quotes(raw_quotes, config.granularity)
    if config.limit and len(aggregated) > config.limit:
        aggregated = aggregated[-config.limit :]

    return MarketEnrichment(
        symbol=symbol,
        ticker=ticker,
        filing_date=filing_date,
        window_start=window_start,
        window_end=window_end,
        granularity=config.granularity,
        quotes=aggregated,
    )


def _derive_date_range(
    docs: Sequence[Document],
    fallback: tuple[date, date],
) -> tuple[date, date]:
    """Derive effective market-date bounds from filing metadata and config."""
    candidates: list[date] = []
    for doc in docs:
        metadata = doc.metadata or {}
        for data in _metadata_sources(metadata):
            for key in _DATE_KEYS:
                parsed = _parse_date_value(data.get(key))
                if parsed:
                    candidates.append(parsed)
    if not candidates:
        return fallback
    start = min(candidates)
    end = max(candidates)
    return (start, end) if start <= end else (end, start)


def _metadata_sources(metadata: JsonDict) -> Iterable[JsonDict]:
    """Collect candidate metadata maps for date extraction."""
    yield metadata
    source = metadata.get("source_metadata")
    if isinstance(source, dict):
        yield source


def _parse_date_value(value: JsonValue) -> date | None:
    """Parse supported date-like values into date objects."""
    if value is None:
        return None
    if isinstance(value, date):
        if isinstance(value, datetime):
            return value.date()
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return datetime.fromisoformat(stripped).date()
        except ValueError:
            pass
        if stripped.endswith("Z"):
            try:
                return datetime.fromisoformat(
                    stripped.replace("Z", "+00:00")
                ).date()
            except ValueError:
                pass
        if stripped.isdigit() and len(stripped) == 8:
            try:
                return datetime.strptime(stripped, "%Y%m%d").date()
            except ValueError:
                pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(stripped, fmt).date()
            except ValueError:
                continue
    return None


def _extract_filing_date(docs: Sequence[Document]) -> date | None:
    """Extract filing date from result metadata sources."""
    for doc in docs:
        metadata = doc.metadata or {}
        for data in _metadata_sources(metadata):
            for key in _FILING_DATE_KEYS:
                parsed = _parse_date_value(data.get(key))
                if parsed:
                    return parsed
    return None


def _extend_window(start: date, end: date) -> tuple[date, date]:
    """Expand a date window by configured pre/post padding days."""
    limit_min = date(1970, 1, 1)
    limit_max = datetime.now(UTC).date()
    window_start = max(start - _WINDOW_DELTA, limit_min)
    window_end = min(end + _WINDOW_DELTA, limit_max)
    if window_end < window_start:
        window_end = window_start
    return window_start, window_end


def _aggregate_quotes(
    quotes: list[MarketQuote],
    granularity: MarketGranularity,
) -> list[MarketQuoteSummary]:
    """Aggregate quote rows by day for windowed metrics."""
    groups: dict[tuple[int, ...], list[MarketQuote]] = {}
    for quote in quotes:
        bucket_key = _bucket_key(granularity, quote.timestamp)
        groups.setdefault(bucket_key, []).append(quote)

    aggregated: list[MarketQuoteSummary] = []
    for bucket_key in sorted(groups):
        bucket = groups[bucket_key]
        count = len(bucket)
        min_ts = min(quote.timestamp for quote in bucket)
        max_ts = max(quote.timestamp for quote in bucket)
        aggregated.append(
            MarketQuoteSummary(
                start_date=datetime.fromtimestamp(min_ts, UTC).date(),
                end_date=datetime.fromtimestamp(max_ts, UTC).date(),
                average_open=round_float(
                    sum(quote.open_price for quote in bucket) / count,
                    places=2,
                )
                or 0.0,
                average_high=round_float(
                    sum(quote.high for quote in bucket) / count,
                    places=2,
                )
                or 0.0,
                average_low=round_float(
                    sum(quote.low for quote in bucket) / count,
                    places=2,
                )
                or 0.0,
                average_close=round_float(
                    sum(quote.close for quote in bucket) / count,
                    places=2,
                )
                or 0.0,
                average_adjclose=round_float(
                    sum(quote.adjclose for quote in bucket) / count,
                    places=2,
                )
                or 0.0,
                average_volume=sum(quote.volume for quote in bucket) / count,
            )
        )
    return aggregated


def _bucket_key(
    granularity: MarketGranularity, timestamp: int
) -> tuple[int, ...]:
    """Build a deterministic bucket key for grouped quote rows."""
    dt = datetime.fromtimestamp(timestamp, UTC)
    if granularity == MarketGranularity.weekly:
        year, week, _ = dt.isocalendar()
        return (year, week)
    if granularity == MarketGranularity.monthly:
        return (dt.year, dt.month)
    return (dt.year, dt.month, dt.day)
