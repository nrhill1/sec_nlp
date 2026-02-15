"""Tests for additional analyze runnables."""

from __future__ import annotations

import pytest

from sec_nlp.core.stats.sector import SectorCorrelation
from sec_nlp.pipelines.presets.analyze.runnables.filing_sentiment_diff import (
    FilingSentimentDiffInput,
    FilingSentimentDiffRunnable,
)
from sec_nlp.pipelines.presets.analyze.runnables.sector_correlation import (
    SectorCorrelationInput,
    SectorCorrelationRunnable,
)


def test_sector_correlation_runnable_identifies_strongest_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strongest pair should use absolute correlation magnitude."""
    from sec_nlp.pipelines.presets.analyze.runnables import (
        sector_correlation as runnable_module,
    )

    def _mock_sector_correlation(
        *args: object, **kwargs: object
    ) -> list[SectorCorrelation]:
        _ = args
        _ = kwargs
        return [
            SectorCorrelation(
                sic_code="SECTOR",
                symbols=["AAA", "BBB", "CCC"],
                correlation_matrix={
                    "AAA": {"AAA": 1.0, "BBB": 0.42, "CCC": -0.91},
                    "BBB": {"AAA": 0.42, "BBB": 1.0, "CCC": 0.35},
                    "CCC": {"AAA": -0.91, "BBB": 0.35, "CCC": 1.0},
                },
            )
        ]

    monkeypatch.setattr(
        runnable_module,
        "sector_correlation",
        _mock_sector_correlation,
    )

    runner = SectorCorrelationRunnable()
    output = runner.invoke(
        SectorCorrelationInput(symbols=["aaa", "BBB", "CCC"], days=120)
    )

    assert output.symbols == ["AAA", "BBB", "CCC"]
    assert output.strongest_pair == ("AAA", "CCC")
    assert output.strongest_correlation == pytest.approx(-0.91)


def test_sector_correlation_runnable_handles_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No sector data should still return normalized symbols."""
    from sec_nlp.pipelines.presets.analyze.runnables import (
        sector_correlation as runnable_module,
    )

    monkeypatch.setattr(
        runnable_module, "sector_correlation", lambda *_, **__: []
    )

    runner = SectorCorrelationRunnable()
    output = runner.invoke(SectorCorrelationInput(symbols=["bbb", "AAA"]))

    assert output.symbols == ["AAA", "BBB"]
    assert output.correlation_matrix == {}
    assert output.strongest_pair is None
    assert output.strongest_correlation is None


def test_filing_sentiment_diff_runnable_computes_deltas() -> None:
    """Runnable should compute topic deltas and risk-factor changes."""
    previous_results = [
        {
            "sentiment": "negative",
            "tags": ["supply_chain", "risk_management"],
            "key_points": ["Supplier risk elevated"],
            "source_metadata": {"topic_hits": ["operational risk"]},
        },
        {
            "sentiment": "neutral",
            "tags": ["liquidity"],
            "key_points": ["Cash position unchanged"],
            "source_metadata": {},
        },
    ]
    current_results = [
        {
            "sentiment": "positive",
            "tags": ["supply_chain"],
            "key_points": ["Supplier risk easing"],
            "source_metadata": {},
        },
        {
            "sentiment": "negative",
            "tags": ["liquidity"],
            "key_points": ["Liquidity risk remains high"],
            "source_metadata": {},
        },
        {
            "sentiment": "positive",
            "tags": ["new_product"],
            "key_points": ["New product launch momentum"],
            "source_metadata": {},
        },
    ]

    runner = FilingSentimentDiffRunnable()
    output = runner.invoke(
        FilingSentimentDiffInput(
            current_results=current_results,
            previous_results=previous_results,
        )
    )

    assert output.per_topic_delta["supply_chain"] == pytest.approx(2.0)
    assert output.per_topic_delta["liquidity"] == pytest.approx(-1.0)
    assert output.per_topic_delta["risk_management"] == pytest.approx(1.0)
    assert output.per_topic_delta["new_product"] == pytest.approx(1.0)
    assert output.overall_sentiment_change == pytest.approx(5 / 6)
    assert output.direction == "improving"
    assert "liquidity risk remains high" in output.new_risk_factors
    assert "operational risk" in output.removed_risk_factors


def test_filing_sentiment_diff_runnable_defaults_for_empty_inputs() -> None:
    """Empty inputs should return a stable no-op diff."""
    runner = FilingSentimentDiffRunnable()
    output = runner.invoke(FilingSentimentDiffInput())

    assert output.per_topic_delta == {}
    assert output.new_risk_factors == []
    assert output.removed_risk_factors == []
    assert output.overall_sentiment_change == 0.0
    assert output.direction == "stable"
