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
