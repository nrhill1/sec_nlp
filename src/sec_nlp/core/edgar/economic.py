# src/sec_nlp/core/edgar/economic.py
"""Economic indicator integration utilities backed by FRED data."""

from __future__ import annotations

import os
from bisect import bisect_left
from datetime import UTC, date, datetime, timedelta
from importlib import import_module
from math import isfinite, sqrt
from statistics import NormalDist
from types import ModuleType
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from sec_nlp.core.market import (
    MarketQuote,
    create_market_retriever,
)
from sec_nlp.core.stats.correlation import (
    CorrExtensionError,
    pearson as corr_pearson,
)
from sec_nlp.types import JsonValue


class EconomicDataError(RuntimeError):
    """Raised when economic data fetching or alignment fails."""


class EconomicSeries(BaseModel):
    """Normalized economic series observations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    series_id: str
    description: str
    observations: list[tuple[str, float]]


class MacroContext(BaseModel):
    """Per-filing macroeconomic context record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filing_date: str
    gdp_growth: float | None = None
    cpi_yoy: float | None = None
    unemployment_rate: float | None = None
    fed_funds_rate: float | None = None
    yield_spread_10y_2y: float | None = None


class MacroSensitivity(BaseModel):
    """Correlation between symbol returns and macro indicator values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    indicator_id: str
    correlation: float
    p_value: float
    window_days: int


_SERIES_FIELD_MAP: dict[str, str] = {
    "GDP": "gdp_growth",
    "CPIAUCSL": "cpi_yoy",
    "UNRATE": "unemployment_rate",
    "FEDFUNDS": "fed_funds_rate",
    "T10Y2Y": "yield_spread_10y_2y",
}


class MarketRangeRetriever(Protocol):
    """Duck-typed retriever required for macro-sensitivity calculations."""

    def retrieve_range(
        self,
        ticker: str,
        date_range: tuple[date, date],
    ) -> list[MarketQuote]: ...


def _load_fred_module() -> ModuleType:
    """Load fred module."""
    try:
        return import_module("fredapi")
    except Exception as exc:  # pragma: no cover - depends on environment
        raise EconomicDataError(
            "fredapi is not available; add/install `fredapi` to use economic indicators."
        ) from exc


def _require_fred_api_key() -> str:
    """Read and validate the configured FRED API key."""
    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        raise EconomicDataError("FRED_API_KEY environment variable is not set.")
    return api_key


def _coerce_date(value: str | date | datetime) -> date:
    """Coerce date-like inputs to date values."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _normalize_observation_date(
    value: JsonValue | date | datetime,
) -> str | None:
    """Normalize observation date."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return date.fromisoformat(cleaned).isoformat()
        except ValueError:
            return None
    return None


def _normalize_observation_value(value: JsonValue) -> float | None:
    """Normalize observation value."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            numeric = float(cleaned)
        except ValueError:
            return None
    else:
        return None
    if not isfinite(numeric):
        return None
    return numeric


def _macro_context_from_series(
    *,
    filing_date: str,
    series_id: str,
    value: float | None,
) -> MacroContext:
    """Build filing-aligned macro context records from one indicator series."""
    if value is None:
        return MacroContext(filing_date=filing_date)

    normalized_series_id = series_id.upper()
    if normalized_series_id == "GDP":
        return MacroContext(filing_date=filing_date, gdp_growth=value)
    if normalized_series_id == "CPIAUCSL":
        return MacroContext(filing_date=filing_date, cpi_yoy=value)
    if normalized_series_id == "UNRATE":
        return MacroContext(filing_date=filing_date, unemployment_rate=value)
    if normalized_series_id == "FEDFUNDS":
        return MacroContext(filing_date=filing_date, fed_funds_rate=value)
    if normalized_series_id == "T10Y2Y":
        return MacroContext(filing_date=filing_date, yield_spread_10y_2y=value)
    return MacroContext(filing_date=filing_date)


def fetch_series(
    series_id: str,
    start_date: str = "",
    end_date: str = "",
) -> EconomicSeries:
    """Fetch a FRED series and normalize it to plain Python structures."""
    normalized_series_id = series_id.strip().upper()
    if not normalized_series_id:
        raise ValueError("series_id must be non-empty")

    fred_module = _load_fred_module()
    fred_client = fred_module.Fred(api_key=_require_fred_api_key())

    query_kwargs: dict[str, str] = {}
    if start_date:
        query_kwargs["observation_start"] = _coerce_date(start_date).isoformat()
    if end_date:
        query_kwargs["observation_end"] = _coerce_date(end_date).isoformat()

    raw_series = fred_client.get_series(normalized_series_id, **query_kwargs)

    observations: list[tuple[str, float]] = []
    for raw_date, raw_value in raw_series.items():
        normalized_date = _normalize_observation_date(raw_date)
        normalized_value = _normalize_observation_value(raw_value)
        if normalized_date is None or normalized_value is None:
            continue
        observations.append((normalized_date, normalized_value))
    observations.sort(key=lambda item: item[0])

    description = normalized_series_id
    try:
        series_info = fred_client.get_series_info(normalized_series_id)
    except Exception:  # pragma: no cover - defensive fallback
        series_info = None
    if series_info is not None:
        title = getattr(series_info, "title", None)
        if isinstance(title, str) and title.strip():
            description = title.strip()

    return EconomicSeries(
        series_id=normalized_series_id,
        description=description,
        observations=observations,
    )


def align_to_filings(
    series: EconomicSeries,
    filing_dates: list[str],
) -> list[MacroContext]:
    """Align each filing date to the nearest available economic observation."""
    if not filing_dates:
        return []

    sorted_observations = sorted(
        (
            (_coerce_date(date_text), value)
            for date_text, value in series.observations
        ),
        key=lambda item: item[0],
    )
    observation_dates = [day for day, _ in sorted_observations]
    observation_values = [value for _, value in sorted_observations]

    contexts: list[MacroContext] = []
    for filing_date_text in filing_dates:
        filing_day = _coerce_date(filing_date_text)
        nearest_value = _nearest_observation_value(
            filing_day,
            observation_dates,
            observation_values,
        )
        contexts.append(
            _macro_context_from_series(
                filing_date=filing_day.isoformat(),
                series_id=series.series_id,
                value=nearest_value,
            )
        )

    return contexts


def _nearest_observation_value(
    filing_day: date,
    observation_dates: list[date],
    observation_values: list[float],
) -> float | None:
    """Return the closest observation value on or before a target date."""
    if not observation_dates:
        return None

    insertion_index = bisect_left(observation_dates, filing_day)
    candidate_indices: list[int] = []
    if insertion_index < len(observation_dates):
        candidate_indices.append(insertion_index)
    if insertion_index > 0:
        candidate_indices.append(insertion_index - 1)

    if not candidate_indices:
        return None

    best_index = min(
        candidate_indices,
        key=lambda idx: abs((observation_dates[idx] - filing_day).days),
    )
    return observation_values[best_index]


def compute_macro_sensitivity(
    symbol: str,
    indicator_id: str,
    window_days: int = 252,
    *,
    retriever: MarketRangeRetriever | None = None,
) -> MacroSensitivity:
    """Compute return/indicator correlation over an aligned trailing window."""
    normalized_symbol = symbol.strip().upper()
    normalized_indicator_id = indicator_id.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must be non-empty")
    if not normalized_indicator_id:
        raise ValueError("indicator_id must be non-empty")
    if window_days < 2:
        raise ValueError("window_days must be >= 2")

    end_day = datetime.now(UTC).date()
    start_day = end_day - timedelta(days=max(window_days * 2, window_days + 30))

    retriever_instance = retriever or create_market_retriever()
    quotes = retriever_instance.retrieve_range(
        normalized_symbol,
        (start_day, end_day),
    )
    if len(quotes) < 3:
        raise EconomicDataError(
            "insufficient market data to compute sensitivity"
        )

    trailing_quotes = quotes[-(window_days + 1) :]
    returns_by_day = _daily_returns(trailing_quotes)
    if len(returns_by_day) < 2:
        raise EconomicDataError("insufficient return observations")

    series = fetch_series(
        normalized_indicator_id,
        start_date=start_day.isoformat(),
        end_date=end_day.isoformat(),
    )
    indicator_by_day = _indicator_values_by_day(series)

    return_values: list[float] = []
    indicator_values: list[float] = []
    for quote_day, return_value in returns_by_day:
        aligned_indicator_value = _latest_indicator_on_or_before(
            quote_day, indicator_by_day
        )
        if aligned_indicator_value is None:
            continue
        return_values.append(return_value)
        indicator_values.append(aligned_indicator_value)

    if len(return_values) < 3 or len(indicator_values) < 3:
        raise EconomicDataError("insufficient aligned observations")

    try:
        correlation = corr_pearson(return_values, indicator_values)
    except CorrExtensionError:
        correlation = _fallback_pearson(return_values, indicator_values)

    return MacroSensitivity(
        symbol=normalized_symbol,
        indicator_id=normalized_indicator_id,
        correlation=correlation,
        p_value=_approximate_p_value(correlation, len(return_values)),
        window_days=window_days,
    )


def _daily_returns(quotes: list[MarketQuote]) -> list[tuple[date, float]]:
    """Compute simple daily returns from ordered close prices."""
    ordered_quotes = sorted(quotes, key=lambda quote: quote.timestamp)
    returns: list[tuple[date, float]] = []
    for previous_quote, current_quote in zip(
        ordered_quotes,
        ordered_quotes[1:],
        strict=False,
    ):
        previous_close = float(previous_quote.close)
        current_close = float(current_quote.close)
        if previous_close == 0:
            continue
        quote_day = datetime.fromtimestamp(
            current_quote.timestamp, tz=UTC
        ).date()
        returns.append((quote_day, (current_close / previous_close) - 1.0))
    return returns


def _indicator_values_by_day(
    series: EconomicSeries,
) -> list[tuple[date, float]]:
    """Map indicator observations to normalized day keys."""
    values: list[tuple[date, float]] = []
    for day_text, value in series.observations:
        values.append((_coerce_date(day_text), value))
    values.sort(key=lambda item: item[0])
    return values


def _latest_indicator_on_or_before(
    day: date,
    indicator_by_day: list[tuple[date, float]],
) -> float | None:
    """Return the latest indicator value on or before a given day."""
    dates = [series_day for series_day, _ in indicator_by_day]
    insertion_index = bisect_left(dates, day)

    if insertion_index < len(dates) and dates[insertion_index] == day:
        return indicator_by_day[insertion_index][1]
    if insertion_index == 0:
        return None
    return indicator_by_day[insertion_index - 1][1]


def _fallback_pearson(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation without optional third-party deps."""
    if len(x) != len(y):
        raise EconomicDataError("series lengths must match for correlation")
    if len(x) < 2:
        raise EconomicDataError("need at least two points for correlation")

    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    numerator = sum(
        (x_value - mean_x) * (y_value - mean_y)
        for x_value, y_value in zip(x, y, strict=False)
    )
    denominator_x = sqrt(sum((x_value - mean_x) ** 2 for x_value in x))
    denominator_y = sqrt(sum((y_value - mean_y) ** 2 for y_value in y))
    denominator = denominator_x * denominator_y
    if denominator == 0:
        raise EconomicDataError("cannot compute correlation with zero variance")
    return numerator / denominator


def _approximate_p_value(correlation: float, sample_size: int) -> float:
    """Approximate a two-tailed p-value from a correlation coefficient."""
    if sample_size <= 2:
        return 1.0
    bounded_r = max(min(correlation, 0.999_999), -0.999_999)
    t_stat = abs(bounded_r) * sqrt((sample_size - 2) / (1.0 - bounded_r**2))
    return max(0.0, min(1.0, 2.0 * (1.0 - NormalDist().cdf(t_stat))))
