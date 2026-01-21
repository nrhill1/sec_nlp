from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sec_nlp.types import ConfigScalar, JsonValue

MARKET_METRIC_CLOSE: ConfigScalar
MARKET_METRIC_VOLUME: ConfigScalar
MARKET_METRIC_RANGE: ConfigScalar
MARKET_METRIC_ADJCLOSE: ConfigScalar
MARKET_METRICS: tuple[ConfigScalar, ...]

MARKET_STYLE_BARS: ConfigScalar
MARKET_STYLE_POINTS: ConfigScalar
MARKET_STYLES: tuple[ConfigScalar, ...]

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
    def range_value(self) -> float: ...

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

def load_market_snapshot(paths: Sequence[Path]) -> MarketSnapshot | None: ...
def extract_market_snapshot(
    payload: JsonValue | None,
) -> MarketSnapshot | None: ...
def select_market_series(
    snapshot: MarketSnapshot, metric: ConfigScalar
) -> list[float]: ...
def build_market_chart_lines(
    values: Sequence[float],
    *,
    width: int,
    height: int,
    style: ConfigScalar,
    normalize: bool,
) -> list[ConfigScalar]: ...
