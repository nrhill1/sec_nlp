"""Tests for sector-level stats correlation helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

import pytest

import sec_nlp.core.stats.sector as sector_module
from sec_nlp.core.market import MarketQuote


class _FakeRetriever(sector_module.MarketRangeRetriever):
    def __init__(self, quotes_by_ticker: dict[str, list[MarketQuote]]) -> None:
        self._quotes_by_ticker = quotes_by_ticker

    def retrieve_range(
        self,
        ticker: str,
        date_range: Sequence[date | datetime],
    ) -> list[MarketQuote]:
        _ = date_range
        return list(self._quotes_by_ticker.get(ticker, []))


def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp())


def _quote(timestamp: int, close: float, volume: int = 100) -> MarketQuote:
    return MarketQuote(
        timestamp=timestamp,
        open_price=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        adjclose=close,
    )


def test_sector_correlation_groups_symbols_by_sic() -> None:
    retriever = _FakeRetriever(
        {
            "AAA": [
                _quote(_ts(2024, 1, 1), 100.0),
                _quote(_ts(2024, 1, 2), 110.0),
                _quote(_ts(2024, 1, 3), 99.0),
                _quote(_ts(2024, 1, 4), 108.9),
            ],
            "BBB": [
                _quote(_ts(2024, 1, 1), 50.0),
                _quote(_ts(2024, 1, 2), 55.0),
                _quote(_ts(2024, 1, 3), 49.5),
                _quote(_ts(2024, 1, 4), 54.45),
            ],
            "CCC": [
                _quote(_ts(2024, 1, 1), 200.0),
                _quote(_ts(2024, 1, 2), 190.0),
                _quote(_ts(2024, 1, 3), 199.5),
                _quote(_ts(2024, 1, 4), 189.525),
            ],
        }
    )
    result = sector_module.sector_correlation(
        ["AAA", "BBB", "CCC"],
        days=10,
        as_of=date(2024, 1, 4),
        symbol_to_sic={"AAA": "3571", "BBB": "3571", "CCC": "2834"},
        retriever=retriever,
    )

    assert len(result) == 2
    by_sic = {row.sic_code: row for row in result}

    assert sorted(by_sic["3571"].symbols) == ["AAA", "BBB"]
    assert by_sic["3571"].correlation_matrix["AAA"]["AAA"] == 1.0
    assert by_sic["3571"].correlation_matrix["BBB"]["BBB"] == 1.0
    assert by_sic["3571"].correlation_matrix["AAA"]["BBB"] == pytest.approx(1.0)

    assert by_sic["2834"].symbols == ["CCC"]
    assert by_sic["2834"].correlation_matrix["CCC"]["CCC"] == 1.0


def test_sector_correlation_uses_fallback_when_corr_missing(
    monkeypatch,
) -> None:
    retriever = _FakeRetriever(
        {
            "AAA": [
                _quote(_ts(2024, 1, 1), 100.0),
                _quote(_ts(2024, 1, 2), 110.0),
                _quote(_ts(2024, 1, 3), 99.0),
                _quote(_ts(2024, 1, 4), 108.9),
            ],
            "BBB": [
                _quote(_ts(2024, 1, 1), 50.0),
                _quote(_ts(2024, 1, 2), 55.0),
                _quote(_ts(2024, 1, 3), 49.5),
                _quote(_ts(2024, 1, 4), 54.45),
            ],
        }
    )

    def _raise_corr_error(_x: list[float], _y: list[float]) -> float:
        raise sector_module.CorrExtensionError("missing")

    monkeypatch.setattr(sector_module, "pearson", _raise_corr_error)

    result = sector_module.sector_correlation(
        ["AAA", "BBB"],
        days=10,
        as_of=date(2024, 1, 4),
        symbol_to_sic={"AAA": "3571", "BBB": "3571"},
        retriever=retriever,
    )

    assert len(result) == 1
    assert result[0].correlation_matrix["AAA"]["BBB"] == pytest.approx(1.0)


def test_sector_correlation_validates_metric() -> None:
    with pytest.raises(ValueError, match="price_return"):
        sector_module.sector_correlation(["AAA"], metric="sentiment")
