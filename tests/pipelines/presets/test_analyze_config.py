# tests/pipelines/presets/test_analyze_config.py
"""Tests for AnalyzeConfig validation."""

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
