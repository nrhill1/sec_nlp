"""Market data retrieval helpers backed by the Rust `market` extension."""

from dataclasses import dataclass
from datetime import date, datetime
from types import ModuleType


class MarketExtensionError(RuntimeError):
    """Raised when the Rust `market` extension is unavailable."""


@dataclass(frozen=True)
class MarketQuote:
    """Market quote data returned by the Rust extension."""

    timestamp: int
    open_price: float
    high: float
    low: float
    close: float
    volume: int
    adjclose: float


def _load_market_module() -> ModuleType:
    try:
        import market as market_module
    except Exception as exc:  # pragma: no cover - depends on extension install
        raise MarketExtensionError(
            "market extension is not available; build it with "
            "`make maturin-dev` or `make market-dev`."
        ) from exc
    return market_module


def _coerce_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("date_range values must be date or datetime")


def _coerce_date_range(date_range):
    if not isinstance(date_range, tuple) and not isinstance(date_range, list):
        raise ValueError("date_range must be a (start, end) sequence")
    if len(date_range) != 2:
        raise ValueError("date_range must contain exactly two values")
    start_date = _coerce_date(date_range[0])
    end_date = _coerce_date(date_range[1])
    if start_date > end_date:
        raise ValueError("date_range end must be >= start")
    return start_date, end_date


class MarketRetriever:
    """Small retrieval helper for Yahoo-backed market data."""

    def __init__(self, module: ModuleType | None = None) -> None:
        self._market = module or _load_market_module()

    def retrieve_range(self, ticker, date_range) -> list[MarketQuote]:
        """Fetch OHLCV quotes for a ticker within a date range.

        Expects a (start_date, end_date) sequence of date/datetime values.
        """
        start_date, end_date = _coerce_date_range(date_range)
        date_range_text = f"{start_date.isoformat()}..{end_date.isoformat()}"
        raw_quotes = self._market.retrieve_range(ticker, date_range_text)
        return [MarketQuote(**quote) for quote in raw_quotes]


def create_market_retriever() -> MarketRetriever:
    """Create a MarketRetriever instance."""
    return MarketRetriever()
