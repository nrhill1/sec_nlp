# tests/cli/test_analyze_presets.py
"""Tests for analyze preset definitions."""

from sec_nlp.pipelines.presets.analyze.profiles import (
    AnalyzePreset,
    get_preset_config,
)


def test_sentiment_preset_is_registered() -> None:
    assert AnalyzePreset.sentiment.value == "sentiment"
    assert "production" in AnalyzePreset.sentiment.description.lower()


def test_deep_preset_is_registered() -> None:
    assert AnalyzePreset.deep.value == "deep"


def test_sentiment_preset_enables_compact_sentiment_profile() -> None:
    config = get_preset_config(AnalyzePreset.sentiment)

    assert config.get("compact_result_output") is True
    assert config.get("analysis_instruction_style") == "compact"
    assert config.get("top_k_chunks") == 24
    assert config.get("max_chunks_per_filing") == 12

    analysis_fields = config.get("analysis_fields")
    assert isinstance(analysis_fields, list)
    assert "sentiment" in analysis_fields
    assert "summary" in analysis_fields


def test_deep_preset_enables_verbose_profile() -> None:
    config = get_preset_config(AnalyzePreset.deep)
    assert config.get("compact_result_output") is False
    assert config.get("analysis_instruction_style") == "full"
    analysis_fields = config.get("analysis_fields")
    assert isinstance(analysis_fields, list)
    assert "reasoning" in analysis_fields
    assert "impact_channels" in analysis_fields
