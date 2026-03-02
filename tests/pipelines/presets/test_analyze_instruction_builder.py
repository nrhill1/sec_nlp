# tests/pipelines/presets/test_analyze_instruction_builder.py
"""Tests for analyze prompt instruction generation."""

from sec_nlp.pipelines.presets.analyze.steps.analysis.instructions import (
    AnalysisInstructionBuilder,
)


def test_instruction_builder_compact_style_reduces_verbosity() -> None:
    instructions = AnalysisInstructionBuilder(
        analysis_fields=["summary", "sentiment"],
        style="compact",
    ).build()

    assert "**summary**" in instructions
    assert "1-2 factual sentences" in instructions
    assert "**sentiment**" in instructions
    assert "0.9-1.0" not in instructions
    assert "**is_relevant**" in instructions
    assert "**confidence_score**" in instructions


def test_instruction_builder_full_style_keeps_detailed_confidence_guidance() -> (
    None
):
    instructions = AnalysisInstructionBuilder(
        analysis_fields=["summary"],
        style="full",
    ).build()

    assert "**summary**" in instructions
    assert "0.9-1.0" in instructions
