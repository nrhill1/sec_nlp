"""Tests for market statistics, sparklines, SMA, and returns computations."""

from sec_nlp.tui.market import (
    MARKET_METRIC_ADJCLOSE,
    MARKET_METRIC_CLOSE,
    MARKET_METRIC_RANGE,
    MARKET_METRIC_RETURNS,
    MARKET_METRIC_VOLUME,
    MARKET_STYLE_BARS,
    MARKET_STYLE_POINTS,
    MarketQuotePoint,
    MarketSnapshot,
    SeriesStats,
    autocorr_lag1,
    build_market_chart_lines,
    build_sparkline,
    calculate_stats,
    compute_returns,
    compute_sma,
    extract_market_snapshot,
    format_stats_lines,
    select_market_series,
)


def _make_snapshot(quotes: list[MarketQuotePoint]) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="TEST",
        ticker="SPY",
        filing_date="2024-01-15",
        window_start="2024-01-01",
        window_end="2024-01-31",
        granularity="daily",
        quotes=tuple(quotes),
        correlation=None,
    )


def _make_quote(
    close: float,
    volume: float = 1000.0,
    high: float | None = None,
    low: float | None = None,
) -> MarketQuotePoint:
    h = high if high is not None else close + 1
    lo = low if low is not None else close - 1
    return MarketQuotePoint(
        start="2024-01-01",
        end="2024-01-02",
        open_value=close,
        high_value=h,
        low_value=lo,
        close_value=close,
        adjclose_value=close,
        volume_value=volume,
    )


class TestComputeReturns:
    def test_empty_returns_empty(self) -> None:
        assert compute_returns([]) == []

    def test_single_value_returns_empty(self) -> None:
        assert compute_returns([100.0]) == []

    def test_simple_returns(self) -> None:
        # 100 -> 110 = 10% return, 110 -> 99 = -10% return
        returns = compute_returns([100.0, 110.0, 99.0])
        assert len(returns) == 2
        assert abs(returns[0] - 0.1) < 1e-9
        assert abs(returns[1] - (-0.1)) < 1e-9

    def test_zero_base_returns_zero(self) -> None:
        # If base is 0, return should be 0
        returns = compute_returns([0.0, 10.0, 20.0])
        assert returns[0] == 0.0
        assert returns[1] == 1.0  # (20-10)/10


class TestComputeSMA:
    def test_empty_returns_empty(self) -> None:
        assert compute_sma([], window=5) == []

    def test_zero_window_returns_empty(self) -> None:
        assert compute_sma([1.0, 2.0, 3.0], window=0) == []

    def test_single_element(self) -> None:
        result = compute_sma([10.0], window=5)
        assert result == [10.0]

    def test_sma_window_larger_than_series(self) -> None:
        result = compute_sma([1.0, 2.0, 3.0], window=10)
        assert len(result) == 3
        assert result[0] == 1.0
        assert result[1] == 1.5
        assert result[2] == 2.0

    def test_sma_exact_window(self) -> None:
        result = compute_sma([2.0, 4.0, 6.0, 8.0, 10.0], window=3)
        assert len(result) == 5
        assert result[0] == 2.0
        assert result[1] == 3.0
        assert result[2] == 4.0
        assert result[3] == 6.0
        assert result[4] == 8.0


class TestBuildSparkline:
    def test_empty_returns_empty(self) -> None:
        assert build_sparkline([], width=10) == ""

    def test_zero_width_returns_empty(self) -> None:
        assert build_sparkline([1.0, 2.0], width=0) == ""

    def test_constant_series_uses_lowest_block(self) -> None:
        result = build_sparkline([5.0, 5.0, 5.0], width=3)
        assert result == "▁▁▁"

    def test_increasing_series(self) -> None:
        result = build_sparkline([1.0, 5.0, 10.0], width=3)
        assert len(result) == 3
        assert result[0] == "▁"
        assert result[2] == "█"

    def test_compression(self) -> None:
        # Width less than series length
        result = build_sparkline([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], width=3)
        assert len(result) == 3


class TestCalculateStats:
    def test_empty_returns_none(self) -> None:
        assert calculate_stats([]) is None

    def test_single_value(self) -> None:
        stats = calculate_stats([100.0])
        assert stats is not None
        assert stats.count == 1
        assert stats.first == 100.0
        assert stats.last == 100.0
        assert stats.min_value == 100.0
        assert stats.max_value == 100.0
        assert stats.mean == 100.0
        assert stats.stddev == 0.0
        assert stats.delta == 0.0
        assert stats.pct_change == 0.0

    def test_multi_value(self) -> None:
        stats = calculate_stats([100.0, 110.0, 90.0, 120.0])
        assert stats is not None
        assert stats.count == 4
        assert stats.first == 100.0
        assert stats.last == 120.0
        assert stats.min_value == 90.0
        assert stats.max_value == 120.0
        assert stats.delta == 20.0
        assert stats.pct_change == 0.2


class TestAutocorrLag1:
    def test_empty_returns_none(self) -> None:
        assert autocorr_lag1([]) is None

    def test_single_value_returns_none(self) -> None:
        assert autocorr_lag1([1.0]) is None

    def test_constant_series(self) -> None:
        # Constant series has zero variance, returns None
        assert autocorr_lag1([5.0, 5.0, 5.0]) is None

    def test_alternating_series(self) -> None:
        # Perfect negative autocorrelation
        result = autocorr_lag1([1.0, -1.0, 1.0, -1.0])
        assert result is not None
        assert result < 0


class TestFormatStatsLines:
    def test_empty_returns_empty(self) -> None:
        assert format_stats_lines([]) == []

    def test_returns_four_lines(self) -> None:
        lines = format_stats_lines([100.0, 110.0, 105.0])
        assert len(lines) == 4
        assert "count 3" in str(lines[0])
        assert "first" in str(lines[0])
        assert "min" in str(lines[1])
        assert "std" in str(lines[2])
        assert "autocorr" in str(lines[3])


class TestSelectMarketSeries:
    def test_close_metric(self) -> None:
        quotes = [_make_quote(100.0), _make_quote(110.0)]
        snapshot = _make_snapshot(quotes)
        series = select_market_series(snapshot, MARKET_METRIC_CLOSE)
        assert series == [100.0, 110.0]

    def test_volume_metric(self) -> None:
        quotes = [
            _make_quote(100.0, volume=1000.0),
            _make_quote(110.0, volume=2000.0),
        ]
        snapshot = _make_snapshot(quotes)
        series = select_market_series(snapshot, MARKET_METRIC_VOLUME)
        assert series == [1000.0, 2000.0]

    def test_range_metric(self) -> None:
        quotes = [
            _make_quote(100.0, high=110.0, low=90.0),
            _make_quote(100.0, high=120.0, low=80.0),
        ]
        snapshot = _make_snapshot(quotes)
        series = select_market_series(snapshot, MARKET_METRIC_RANGE)
        assert series == [20.0, 40.0]

    def test_adjclose_metric(self) -> None:
        quotes = [_make_quote(100.0), _make_quote(110.0)]
        snapshot = _make_snapshot(quotes)
        series = select_market_series(snapshot, MARKET_METRIC_ADJCLOSE)
        assert series == [100.0, 110.0]

    def test_returns_metric(self) -> None:
        quotes = [_make_quote(100.0), _make_quote(110.0), _make_quote(99.0)]
        snapshot = _make_snapshot(quotes)
        series = select_market_series(snapshot, MARKET_METRIC_RETURNS)
        assert len(series) == 2
        assert abs(series[0] - 0.1) < 1e-9
        assert abs(series[1] - (-0.1)) < 1e-9


class TestBuildMarketChartLines:
    def test_empty_returns_empty(self) -> None:
        assert (
            build_market_chart_lines(
                [], width=10, height=5, style=MARKET_STYLE_BARS, normalize=True
            )
            == []
        )

    def test_zero_dimensions_returns_empty(self) -> None:
        assert (
            build_market_chart_lines(
                [1.0],
                width=0,
                height=5,
                style=MARKET_STYLE_BARS,
                normalize=True,
            )
            == []
        )
        assert (
            build_market_chart_lines(
                [1.0],
                width=5,
                height=0,
                style=MARKET_STYLE_BARS,
                normalize=True,
            )
            == []
        )

    def test_bars_style(self) -> None:
        lines = build_market_chart_lines(
            [1.0, 2.0, 3.0],
            width=3,
            height=3,
            style=MARKET_STYLE_BARS,
            normalize=True,
        )
        assert len(lines) == 3
        assert "#" in str(lines[-1])

    def test_points_style(self) -> None:
        lines = build_market_chart_lines(
            [1.0, 2.0, 3.0],
            width=3,
            height=3,
            style=MARKET_STYLE_POINTS,
            normalize=True,
        )
        assert len(lines) == 3
        assert "*" in "".join(str(line) for line in lines)

    def test_overlay_produces_dashes(self) -> None:
        lines = build_market_chart_lines(
            [1.0, 2.0, 3.0, 4.0, 5.0],
            width=5,
            height=5,
            style=MARKET_STYLE_BARS,
            normalize=True,
            overlay=[2.0, 2.5, 3.0, 3.5, 4.0],
        )
        all_text = "".join(str(line) for line in lines)
        # Overlay should produce "-" characters
        assert "-" in all_text


class TestExtractMarketSnapshot:
    def test_none_payload_returns_none(self) -> None:
        assert extract_market_snapshot(None) is None

    def test_missing_market_enrichment_returns_none(self) -> None:
        assert extract_market_snapshot({}) is None

    def test_missing_required_fields_returns_none(self) -> None:
        payload = {"market_enrichment": {"symbol": "AAPL"}}
        assert extract_market_snapshot(payload) is None

    def test_empty_quotes_returns_none(self) -> None:
        payload = {
            "market_enrichment": {
                "symbol": "AAPL",
                "ticker": "SPY",
                "window_start": "2024-01-01",
                "window_end": "2024-01-31",
                "granularity": "daily",
                "quotes": [],
            }
        }
        assert extract_market_snapshot(payload) is None

    def test_valid_payload_extracts_snapshot(self) -> None:
        payload = {
            "market_enrichment": {
                "symbol": "AAPL",
                "ticker": "SPY",
                "filing_date": "2024-01-15",
                "window_start": "2024-01-01",
                "window_end": "2024-01-31",
                "granularity": "daily",
                "quotes": [
                    {
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-02",
                        "average_open": 100.0,
                        "average_high": 110.0,
                        "average_low": 95.0,
                        "average_close": 105.0,
                        "average_adjclose": 105.0,
                        "average_volume": 1000000.0,
                    },
                ],
            },
            "market_correlation": "correlation text",
        }
        snapshot = extract_market_snapshot(payload)
        assert snapshot is not None
        assert snapshot.symbol == "AAPL"
        assert snapshot.ticker == "SPY"
        assert snapshot.correlation == "correlation text"
        assert len(snapshot.quotes) == 1
