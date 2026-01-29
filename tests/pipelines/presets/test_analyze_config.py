# tests/pipelines/presets/test_analyze_config.py
"""Tests for AnalyzeConfig validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from sec_nlp.pipelines.presets.analyze import AnalyzeConfig


def test_analyze_config_rejects_malicious_run_id() -> None:
    """Non-numeric or injection-style run_id values should be rejected."""
    with pytest.raises((ValidationError, ValueError)):
        # NOTE: Intentional SQL injection string for testing validation.
        # This should be rejected by Pydantic validators.
        AnalyzeConfig.model_validate(
            {"symbols": ["AAPL"], "run_id": "1; DROP TABLE runs;"}
        )


def test_proxy_default_topics_apply_when_empty() -> None:
    config = AnalyzeConfig.model_validate(
        {"symbols": ["AAPL"], "mode": "proxy"}
    )
    assert "executive compensation" in config.topics


def test_proxy_default_topics_do_not_override_cli() -> None:
    config = AnalyzeConfig.model_validate(
        {
            "symbols": ["AAPL"],
            "mode": "proxy",
            "topics": ["custom governance topic"],
        }
    )
    assert config.topics == ["custom governance topic"]


def test_analyze_config_defaults_to_semantic_chunking(
    tmp_path: Path,
) -> None:
    config = AnalyzeConfig(
        symbols=["AAPL"],
        out_path=tmp_path,
        dl_path=tmp_path,
    )
    assert config.chunking_mode == "semantic"


def test_llm_partial_override_preserves_prompt_file(tmp_path: Path) -> None:
    """Overriding llm.model_name should not lose the default prompt_file.

    This guards against a regression where CLI --llm.model-name would
    create a partial LLMConfig dict that overrides the default_factory,
    losing the default prompt_file and causing validation errors.
    """
    config = AnalyzeConfig.model_validate(
        {
            "symbols": ["AAPL"],
            "out_path": str(tmp_path),
            "dl_path": str(tmp_path),
            "llm": {"model_name": "llama3.2:3b"},
        }
    )
    assert config.llm.model_name == "llama3.2:3b"
    # prompt_file should be preserved from defaults
    assert config.llm.prompt_file is not None
    assert config.llm.prompt_file.exists()


def test_llm_explicit_prompt_file_not_overridden(tmp_path: Path) -> None:
    """Explicitly provided prompt_file should not be replaced by default."""
    custom_prompt = tmp_path / "custom_prompt.yaml"
    custom_prompt.write_text("system: test\n")

    config = AnalyzeConfig.model_validate(
        {
            "symbols": ["AAPL"],
            "out_path": str(tmp_path),
            "dl_path": str(tmp_path),
            "llm": {
                "model_name": "llama3.2:3b",
                "prompt_file": str(custom_prompt),
            },
        }
    )
    assert config.llm.prompt_file == custom_prompt


def test_llm_defaults_when_not_provided(tmp_path: Path) -> None:
    """LLM config should use defaults when not provided at all."""
    config = AnalyzeConfig(
        symbols=["AAPL"],
        out_path=tmp_path,
        dl_path=tmp_path,
    )
    # Should have default prompt_file
    assert config.llm.prompt_file is not None
    assert config.llm.prompt_file.exists()
