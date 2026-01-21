"""Market data helpers for the TUI."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sec_nlp.core.types import coerce_float, coerce_json_dict
from sec_nlp.types import ConfigScalar, JsonValue

MARKET_METRIC_CLOSE = "close"
MARKET_METRIC_VOLUME = "volume"
MARKET_METRIC_RANGE = "range"
MARKET_METRIC_ADJCLOSE = "adjclose"
MARKET_METRICS: tuple[ConfigScalar, ...] = (
    MARKET_METRIC_CLOSE,
    MARKET_METRIC_VOLUME,
    MARKET_METRIC_RANGE,
    MARKET_METRIC_ADJCLOSE,
)

MARKET_STYLE_BARS = "bars"
MARKET_STYLE_POINTS = "points"
MARKET_STYLES: tuple[ConfigScalar, ...] = (
    MARKET_STYLE_BARS,
    MARKET_STYLE_POINTS,
)


@dataclass(frozen=True)
class MarketQuotePoint:
    start: ConfigScalar
    end: ConfigScalar
    open_value: float
    high_value: float
    low_value: float
    close_value: float
    adjclose_value: float
    volume_value: float

    def range_value(self) -> float:
        return self.high_value - self.low_value


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: ConfigScalar
    ticker: ConfigScalar
    filing_date: ConfigScalar | None
    window_start: ConfigScalar
    window_end: ConfigScalar
    granularity: ConfigScalar
    quotes: tuple[MarketQuotePoint, ...]
    correlation: ConfigScalar | None


def load_market_snapshot(paths: Sequence[Path]) -> MarketSnapshot | None:
    candidates = _sorted_existing_paths(paths)
    for path in candidates:
        payload = _load_payload(path)
        snapshot = extract_market_snapshot(payload)
        if snapshot is not None:
            return snapshot
    return None


def extract_market_snapshot(payload: JsonValue | None) -> MarketSnapshot | None:
    if payload is None:
        return None
    payload_dict = coerce_json_dict(payload)
    if payload_dict is None:
        return None

    market_value = payload_dict.get("market_enrichment")
    market = (
        coerce_json_dict(market_value) if market_value is not None else None
    )
    if market is None:
        return None

    symbol = _stringify(market.get("symbol"))
    ticker = _stringify(market.get("ticker"))
    window_start = _stringify(market.get("window_start"))
    window_end = _stringify(market.get("window_end"))
    granularity = _stringify(market.get("granularity"))
    filing_date = _stringify(market.get("filing_date"))
    if (
        symbol is None
        or ticker is None
        or window_start is None
        or window_end is None
        or granularity is None
    ):
        return None

    quotes_value = market.get("quotes")
    if not isinstance(quotes_value, list):
        return None

    quotes: list[MarketQuotePoint] = []
    for item in quotes_value:
        if not isinstance(item, dict):
            continue
        start = _stringify(item.get("start_date"))
        end = _stringify(item.get("end_date"))
        open_value = _coerce_float(item.get("average_open"))
        high_value = _coerce_float(item.get("average_high"))
        low_value = _coerce_float(item.get("average_low"))
        close_value = _coerce_float(item.get("average_close"))
        adjclose_value = _coerce_float(item.get("average_adjclose"))
        volume_value = _coerce_float(item.get("average_volume"))
        if (
            start is None
            or end is None
            or open_value is None
            or high_value is None
            or low_value is None
            or close_value is None
            or adjclose_value is None
            or volume_value is None
        ):
            continue
        quotes.append(
            MarketQuotePoint(
                start=start,
                end=end,
                open_value=open_value,
                high_value=high_value,
                low_value=low_value,
                close_value=close_value,
                adjclose_value=adjclose_value,
                volume_value=volume_value,
            )
        )

    if not quotes:
        return None

    correlation = _stringify(payload_dict.get("market_correlation"))
    return MarketSnapshot(
        symbol=symbol,
        ticker=ticker,
        filing_date=filing_date,
        window_start=window_start,
        window_end=window_end,
        granularity=granularity,
        quotes=tuple(quotes),
        correlation=correlation,
    )


def select_market_series(
    snapshot: MarketSnapshot, metric: ConfigScalar
) -> list[float]:
    if metric == MARKET_METRIC_VOLUME:
        return [quote.volume_value for quote in snapshot.quotes]
    if metric == MARKET_METRIC_RANGE:
        return [quote.range_value() for quote in snapshot.quotes]
    if metric == MARKET_METRIC_ADJCLOSE:
        return [quote.adjclose_value for quote in snapshot.quotes]
    return [quote.close_value for quote in snapshot.quotes]


def build_market_chart_lines(
    values: Sequence[float],
    *,
    width: int,
    height: int,
    style: ConfigScalar,
    normalize: bool,
) -> list[ConfigScalar]:
    if not values or width <= 0 or height <= 0:
        return []

    series = _compress_series(values, width)
    if not series:
        return []

    min_value = min(series)
    max_value = max(series)
    if not normalize:
        if min_value > 0:
            min_value = 0.0
        elif max_value < 0:
            max_value = 0.0
    scale = max_value - min_value if max_value != min_value else 1.0
    levels = [
        int(round((value - min_value) / scale * (height - 1)))
        for value in series
    ]

    lines: list[ConfigScalar] = []
    for row in range(height - 1, -1, -1):
        chars: list[str] = []
        for level in levels:
            if style == MARKET_STYLE_POINTS:
                chars.append("*" if level == row else " ")
            else:
                chars.append("#" if level >= row else " ")
        lines.append("".join(chars).rstrip())
    return lines


def _compress_series(values: Sequence[float], width: int) -> list[float]:
    if len(values) <= width:
        return list(values)
    step = len(values) / width
    compressed: list[float] = []
    for idx in range(width):
        start = int(idx * step)
        end = int((idx + 1) * step)
        if end <= start:
            end = start + 1
        bucket = values[start:end]
        compressed.append(sum(bucket) / len(bucket))
    return compressed


def _sorted_existing_paths(paths: Sequence[Path]) -> list[Path]:
    candidates: list[tuple[float, Path]] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        candidates.append((stat.st_mtime, path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in candidates]


def _load_payload(path: Path) -> JsonValue | None:
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            return None
        try:
            return yaml.safe_load(text)
        except Exception:
            return None

    return None


def _stringify(value: JsonValue) -> ConfigScalar | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _coerce_float(value: JsonValue) -> float | None:
    return coerce_float(value)
