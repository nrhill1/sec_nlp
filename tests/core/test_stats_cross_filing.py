"""Tests for cross-filing stats trend helpers."""

from __future__ import annotations

import pytest

import sec_nlp.core.stats.cross_filing as cross_filing_module
from sec_nlp.pipelines.types import AnalysisResultDict


def _result(
    accession: str,
    filing_date: str,
    sentiment: str,
    *,
    symbol: str = "ACME",
    form_type: str = "10-K",
) -> AnalysisResultDict:
    return {
        "sentiment": sentiment,
        "source_metadata": {
            "accession_number": accession,
            "filing_date": filing_date,
            "symbol": symbol,
            "form_type": form_type,
        },
    }


def test_cross_filing_trend_reports_improving_direction() -> None:
    results = [
        _result("0001", "2024-01-01", "negative"),
        _result("0002", "2025-01-01", "neutral"),
        _result("0003", "2026-01-01", "positive"),
    ]

    trend = cross_filing_module.cross_filing_trend(
        "ACME",
        results,
        form_type="10-K",
        periods=5,
    )

    assert trend.symbol == "ACME"
    assert trend.filings == ["0001", "0002", "0003"]
    assert trend.sentiment_scores == [-1.0, 0.0, 1.0]
    assert trend.trend_direction == "improving"
    assert trend.inflection_points == []


def test_cross_filing_trend_detects_inflections() -> None:
    results = [
        _result("0001", "2023-01-01", "negative"),
        _result("0002", "2024-01-01", "positive"),
        _result("0003", "2025-01-01", "negative"),
        _result("0004", "2026-01-01", "positive"),
    ]

    trend = cross_filing_module.cross_filing_trend("ACME", results)

    assert trend.filings == ["0001", "0002", "0003", "0004"]
    assert trend.sentiment_scores == [-1.0, 1.0, -1.0, 1.0]
    assert trend.inflection_points == [2, 3]


def test_cross_filing_trend_filters_symbol_form_and_periods() -> None:
    results = [
        _result("0001", "2024-01-01", "negative"),
        _result("0002", "2025-01-01", "neutral"),
        _result("0003", "2026-01-01", "positive"),
        _result("0004", "2027-01-01", "positive", form_type="10-Q"),
        _result("0005", "2028-01-01", "negative", symbol="OTHER"),
    ]

    trend = cross_filing_module.cross_filing_trend(
        "ACME",
        results,
        form_type="10-K",
        periods=2,
    )

    assert trend.filings == ["0002", "0003"]
    assert trend.sentiment_scores == [0.0, 1.0]


def test_cross_filing_trend_validates_periods() -> None:
    with pytest.raises(ValueError, match="periods must be > 0"):
        cross_filing_module.cross_filing_trend("ACME", [], periods=0)
