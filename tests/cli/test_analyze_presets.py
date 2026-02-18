"""Tests for analyze preset definitions."""

from sec_nlp.cli.presets import AnalyzePreset, get_preset_config


def test_sentiment_preset_is_registered() -> None:
    assert AnalyzePreset.sentiment.value == "sentiment"


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
