# tests/pipelines/test_llm_config.py
"""Tests for LLMConfig behaviors."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from sec_nlp.pipelines.llm import LLMConfig
from sec_nlp.types import JsonDict, JsonValue


class DummyOllamaLLM:  # pragma: no cover - only used for import compatibility
    pass


class TestLLMConfig:
    """Unit tests for LLMConfig."""

    def test_ollama_model_name_strips_prefix(self) -> None:
        """_ollama_model_name removes provider prefix."""
        config = LLMConfig(model_name="ollama:my-model")

        assert config._ollama_model_name == "my-model"

    def test_ollama_model_name_no_prefix(self) -> None:
        """_ollama_model_name returns original when no prefix."""
        config = LLMConfig(model_name="local-model")

        assert config._ollama_model_name == "local-model"

    def test_prompt_path_with_custom_file(self, tmp_path: Path) -> None:
        """Custom prompt_file should be returned when it exists."""
        prompt = tmp_path / "custom.yaml"
        prompt.write_text("content: test")

        config = LLMConfig(prompt_file=prompt)

        assert config.prompt_path == prompt

    def test_prompt_path_raises_on_missing_custom_file(self) -> None:
        """Missing custom prompt_file raises ValueError."""
        missing = Path("/tmp/does-not-exist.yaml")
        config = LLMConfig(prompt_file=missing)

        with pytest.raises(ValueError, match="Prompt file not found"):
            _ = config.prompt_path

    def test_setup_ollama_model_rejects_non_ollama(self) -> None:
        """Unsupported providers raise a RuntimeError."""
        config = LLMConfig(model_name="openai:gpt-4")

        with pytest.raises(RuntimeError, match="not supported"):
            config.setup_ollama_model()

    def test_setup_ollama_model_invokes_builder(self) -> None:
        """setup_ollama_model forwards args to build_ollama_llm."""
        captured: JsonDict = {}

        class _FakeLLM:
            pass

        fake_llm = _FakeLLM()

        def fake_builder(**kwargs: JsonValue) -> _FakeLLM:
            captured.update(kwargs)
            return fake_llm

        with patch("sec_nlp.core.llm.build_ollama_llm", fake_builder):
            config = LLMConfig(
                model_name="ollama:qwen",
                temperature=0.25,
                require_json=False,
                ollama_kwargs={"keep_alive": 10},
            )

            llm = config.setup_ollama_model()

        assert llm is fake_llm
        assert captured["model_name"] == "qwen"
        assert captured["temperature"] == 0.25
        assert captured["format"] == ""
        assert captured["keep_alive"] == 10
