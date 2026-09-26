# tests/pipelines/presets/test_analyze_result.py
"""Tests for analyze pipeline result parsing."""

from sec_nlp.pipelines.presets.analyze.models import AnalysisResult


def test_key_points_allows_none() -> None:
    """LLM outputs with null key_points should coerce to an empty list."""
    result = AnalysisResult.model_validate({"key_points": None})

    assert result.key_points == []
    assert result.is_relevant is False
