"""Market data helpers for the TUI."""

from __future__ import annotations

import json
import math
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
MARKET_METRIC_RETURNS = "returns"
MARKET_METRICS: tuple[ConfigScalar, ...] = (
    MARKET_METRIC_CLOSE,
    MARKET_METRIC_VOLUME,
    MARKET_METRIC_RANGE,
    MARKET_METRIC_ADJCLOSE,
    MARKET_METRIC_RETURNS,
)

MARKET_STYLE_BARS = "bars"
MARKET_STYLE_POINTS = "points"
MARKET_STYLE_CANDLE = "candle"
MARKET_STYLE_LINE = "line"
MARKET_STYLES: tuple[ConfigScalar, ...] = (
    MARKET_STYLE_BARS,
    MARKET_STYLE_POINTS,
    MARKET_STYLE_CANDLE,
    MARKET_STYLE_LINE,
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
    if metric == MARKET_METRIC_RETURNS:
        prices = [quote.close_value for quote in snapshot.quotes]
        return compute_returns(prices)
    return [quote.close_value for quote in snapshot.quotes]


def build_market_chart_lines(
    values: Sequence[float],
    *,
    width: int,
    height: int,
    style: ConfigScalar,
    normalize: bool,
    overlay: Sequence[float] | None = None,
    quotes: Sequence[MarketQuotePoint] | None = None,
) -> list[str]:
    """Build ASCII chart lines, optionally with an overlay (e.g. SMA).

    For candlestick style, pass quotes with OHLC data.
    """
    if not values or width <= 0 or height <= 0:
        return []

    # Use candlestick rendering if style is candle and we have OHLC data
    if style == MARKET_STYLE_CANDLE and quotes:
        return _build_candlestick_chart(quotes, width, height, normalize)

    if style == MARKET_STYLE_LINE:
        return _build_line_chart(values, width, height, normalize, overlay)

    series = _compress_series(values, width)
    if not series:
        return []

    # Compute overlay levels if provided
    overlay_levels: list[int] | None = None
    if overlay:
        overlay_compressed = _compress_series(overlay, width)
        all_vals = list(series) + list(overlay_compressed)
    else:
        all_vals = list(series)

    min_value = min(all_vals)
    max_value = max(all_vals)
    if not normalize:
        if min_value > 0:
            min_value = 0.0
        elif max_value < 0:
            max_value = 0.0
    scale = max_value - min_value if max_value != min_value else 1.0

    def to_level(v: float) -> int:
        return int(round((v - min_value) / scale * (height - 1)))

    levels = [to_level(v) for v in series]
    if overlay:
        overlay_compressed = _compress_series(overlay, width)
        overlay_levels = [to_level(v) for v in overlay_compressed]

    lines: list[str] = []
    for row in range(height - 1, -1, -1):
        chars: list[str] = []
        for idx, level in enumerate(levels):
            ov_hit = overlay_levels is not None and overlay_levels[idx] == row
            if ov_hit:
                chars.append("─")  # overlay marker (nicer dash)
            elif style == MARKET_STYLE_POINTS:
                chars.append("●" if level == row else " ")
            else:
                # Gradient bars using block characters
                if level >= row:
                    # Use different characters based on position in bar
                    if row == level:
                        chars.append("█")
                    elif row == 0:
                        chars.append("▄")
                    else:
                        chars.append("█")
                else:
                    chars.append(" ")
        lines.append("".join(chars).rstrip())
    return lines


def _build_candlestick_chart(
    quotes: Sequence[MarketQuotePoint],
    width: int,
    height: int,
    normalize: bool,
) -> list[str]:
    """Build candlestick-style chart from OHLC data.

    Uses unicode box-drawing characters:
    - │ for wick (high-low range)
    - █ for bullish body (close > open) - green implied
    - ░ for bearish body (close < open) - red implied
    """
    if not quotes:
        return []

    # Compress quotes to fit width
    compressed = _compress_quotes(quotes, width)
    if not compressed:
        return []

    # Find price range
    all_prices: list[float] = []
    for q in compressed:
        all_prices.extend(
            [q.high_value, q.low_value, q.open_value, q.close_value]
        )

    min_price = min(all_prices)
    max_price = max(all_prices)
    if not normalize:
        if min_price > 0:
            min_price = 0.0
    scale = max_price - min_price if max_price != min_price else 1.0

    def to_level(v: float) -> int:
        return int(round((v - min_price) / scale * (height - 1)))

    lines: list[str] = []
    for row in range(height - 1, -1, -1):
        chars: list[str] = []
        for q in compressed:
            high_level = to_level(q.high_value)
            low_level = to_level(q.low_value)
            open_level = to_level(q.open_value)
            close_level = to_level(q.close_value)
            body_top = max(open_level, close_level)
            body_bottom = min(open_level, close_level)
            bullish = q.close_value >= q.open_value

            if body_bottom <= row <= body_top:
                # Body region
                chars.append("█" if bullish else "░")
            elif low_level <= row <= high_level:
                # Wick region
                chars.append("│")
            else:
                chars.append(" ")
        lines.append("".join(chars).rstrip())
    return lines


def _build_line_chart(
    values: Sequence[float],
    width: int,
    height: int,
    normalize: bool,
    overlay: Sequence[float] | None = None,
) -> list[str]:
    """Build a smooth line chart using braille-like characters."""
    series = _compress_series(values, width)
    if not series:
        return []

    all_vals = list(series)
    if overlay:
        overlay_compressed = _compress_series(overlay, width)
        all_vals.extend(overlay_compressed)
    else:
        overlay_compressed = None

    min_value = min(all_vals)
    max_value = max(all_vals)
    if not normalize:
        if min_value > 0:
            min_value = 0.0
        elif max_value < 0:
            max_value = 0.0
    scale = max_value - min_value if max_value != min_value else 1.0

    def to_level(v: float) -> int:
        return int(round((v - min_value) / scale * (height - 1)))

    levels = [to_level(v) for v in series]
    overlay_levels = (
        [to_level(v) for v in overlay_compressed]
        if overlay_compressed
        else None
    )

    # Line drawing characters for connections
    # ╱ ╲ ─ for diagonal, horizontal connections
    lines: list[str] = []
    for row in range(height - 1, -1, -1):
        chars: list[str] = []
        for idx, level in enumerate(levels):
            ov_hit = overlay_levels is not None and overlay_levels[idx] == row
            if ov_hit and level != row:
                chars.append("┄")  # overlay line
            elif level == row:
                # Determine connection style
                prev_level = levels[idx - 1] if idx > 0 else level
                next_level = levels[idx + 1] if idx < len(levels) - 1 else level
                if prev_level < level and next_level < level:
                    chars.append("╱")  # peak
                elif prev_level > level and next_level > level:
                    chars.append("╲")  # valley
                elif prev_level < level:
                    chars.append("╱")
                elif next_level < level:
                    chars.append("╲")
                else:
                    chars.append("─")
            else:
                chars.append(" ")
        lines.append("".join(chars).rstrip())
    return lines


def _compress_quotes(
    quotes: Sequence[MarketQuotePoint], width: int
) -> list[MarketQuotePoint]:
    """Compress quotes to fit within width, averaging OHLC values."""
    if len(quotes) <= width:
        return list(quotes)
    step = len(quotes) / width
    compressed: list[MarketQuotePoint] = []
    for idx in range(width):
        start = int(idx * step)
        end = int((idx + 1) * step)
        if end <= start:
            end = start + 1
        bucket = quotes[start:end]
        if not bucket:
            continue
        # Aggregate: first open, max high, min low, last close
        compressed.append(
            MarketQuotePoint(
                start=bucket[0].start,
                end=bucket[-1].end,
                open_value=bucket[0].open_value,
                high_value=max(q.high_value for q in bucket),
                low_value=min(q.low_value for q in bucket),
                close_value=bucket[-1].close_value,
                adjclose_value=bucket[-1].adjclose_value,
                volume_value=sum(q.volume_value for q in bucket) / len(bucket),
            )
        )
    return compressed


def build_sparkline(values: Sequence[float], width: int) -> str:
    """Return a one-line sparkline using block characters.

    Uses levels ▁▂▃▄▅▆▇█ to convey relative magnitude.
    """
    blocks = "▁▂▃▄▅▆▇█"
    if not values or width <= 0:
        return ""
    series = _compress_series(values, width)
    if not series:
        return ""
    lo = min(series)
    hi = max(series)
    if hi == lo:
        return blocks[0] * len(series)
    chars: list[str] = []
    for v in series:
        idx = int((v - lo) / (hi - lo) * (len(blocks) - 1))
        chars.append(blocks[idx])
    return "".join(chars)


@dataclass(frozen=True)
class SeriesStats:
    count: int
    first: float
    last: float
    min_value: float
    max_value: float
    mean: float
    stddev: float
    delta: float
    pct_change: float
    autocorr_lag1: float | None


def compute_returns(values: Sequence[float]) -> list[float]:
    if len(values) < 2:
        return []
    returns: list[float] = []
    prev = values[0]
    for cur in values[1:]:
        if prev == 0:
            returns.append(0.0)
        else:
            returns.append((cur - prev) / abs(prev))
        prev = cur
    return returns


def compute_sma(values: Sequence[float], window: int = 5) -> list[float]:
    """Compute simple moving average with given window."""
    if not values or window < 1:
        return []
    n = len(values)
    sma: list[float] = []
    for i in range(n):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        sma.append(sum(chunk) / len(chunk))
    return sma


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float], mean: float | None = None) -> float:
    if not values:
        return 0.0
    mu = _mean(values) if mean is None else mean
    var = sum((v - mu) ** 2 for v in values) / len(values)
    return math.sqrt(var)


def autocorr_lag1(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    x = values
    mu = _mean(x)
    num = sum((x[i] - mu) * (x[i - 1] - mu) for i in range(1, len(x)))
    den = sum((v - mu) ** 2 for v in x)
    if den == 0:
        return None
    return num / den


def calculate_stats(values: Sequence[float]) -> SeriesStats | None:
    if not values:
        return None
    first = values[0]
    last = values[-1]
    mu = _mean(values)
    sd = _stddev(values, mu)
    delt = last - first
    pct = (delt / abs(first)) if first != 0 else 0.0
    return SeriesStats(
        count=len(values),
        first=first,
        last=last,
        min_value=min(values),
        max_value=max(values),
        mean=mu,
        stddev=sd,
        delta=delt,
        pct_change=pct,
        autocorr_lag1=autocorr_lag1(values),
    )


def format_stats_lines(values: Sequence[float]) -> list[str]:
    stats = calculate_stats(values)
    if stats is None:
        return []

    def f(x: float) -> str:
        return f"{x:.4f}"

    ac = f(stats.autocorr_lag1) if stats.autocorr_lag1 is not None else "n/a"
    lines = [
        f"count {stats.count} | first {f(stats.first)} | last {f(stats.last)}",
        f"min {f(stats.min_value)} | max {f(stats.max_value)} | mean {f(stats.mean)}",
        f"std {f(stats.stddev)} | delta {f(stats.delta)} | pct {stats.pct_change * 100:.2f}%",
        f"autocorr(lag1) {ac}",
    ]
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
