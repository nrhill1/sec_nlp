# tests/pipelines/presets/test_analyze_analysis_runner.py
"""Tests for analyze analysis runner helpers."""

from sec_nlp.pipelines.presets.analyze.steps.analysis.analysis_runner import (
    AnalyzerRunnable,
)


def test_numeric_signal_detection_classmethod() -> None:
    assert AnalyzerRunnable._has_numeric_signal("Costs were $5 million")
    assert AnalyzerRunnable._has_numeric_signal(
        "Revenue grew 10% year over year"
    )
    assert not AnalyzerRunnable._has_numeric_signal("No digits here", "")
    assert not AnalyzerRunnable._has_numeric_signal(None)
