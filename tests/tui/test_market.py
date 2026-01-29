from sec_nlp.tui.market import (
    MARKET_METRIC_CLOSE,
    MARKET_STYLE_BARS,
    build_market_chart_lines,
    extract_market_snapshot,
    select_market_series,
)


def test_extract_market_snapshot_parses_quotes() -> None:
    payload = {
        "market_enrichment": {
            "symbol": "AAPL",
            "ticker": "SPY",
            "filing_date": "2024-01-10",
            "window_start": "2023-12-01",
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
                {
                    "start_date": "2024-01-03",
                    "end_date": "2024-01-04",
                    "average_open": 102.0,
                    "average_high": 112.0,
                    "average_low": 98.0,
                    "average_close": 108.0,
                    "average_adjclose": 108.0,
                    "average_volume": 1200000.0,
                },
            ],
        },
        "market_correlation": "filing 2024-01-10 | market SPY daily",
    }

    snapshot = extract_market_snapshot(payload)
    assert snapshot is not None
    assert snapshot.ticker == "SPY"
    assert snapshot.window_start == "2023-12-01"
    assert len(snapshot.quotes) == 2
    series = select_market_series(snapshot, MARKET_METRIC_CLOSE)
    assert series == [105.0, 108.0]


def test_build_market_chart_lines_returns_rows() -> None:
    lines = build_market_chart_lines(
        [1.0, 2.0, 3.0],
        width=3,
        height=3,
        style=MARKET_STYLE_BARS,
        normalize=True,
    )
    assert len(lines) == 3
    # Uses Unicode block characters now (█ or ▄)
    all_text = "".join(str(line) for line in lines)
    assert "█" in all_text or "▄" in all_text
