# tests/pipelines/test_frozen_validation.py
"""Test that frozen=True is enforced on base classes."""

import pytest
from pydantic import ConfigDict
from pydantic_settings import SettingsConfigDict

from sec_nlp.pipelines.base import BasePipeline, BasePipelineResult
from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.types import JsonObject


def test_base_result_frozen_override_raises() -> None:
    """Test that overriding frozen=True in BasePipelineResult subclass raises TypeError."""
    with pytest.raises(TypeError, match="must not override frozen=True"):

        class BadResult(BasePipelineResult):
            pipeline_type = "bad"
            model_config = ConfigDict(frozen=False)


def test_base_config_frozen_override_raises() -> None:
    """Test that overriding frozen=True in BasePipelineSettings subclass raises TypeError."""
    with pytest.raises(TypeError, match="must not override frozen=True"):

        class BadConfig(BasePipelineSettings):
            pipeline_type = "bad"
            model_config = SettingsConfigDict(frozen=False)

            def pipeline_label(self) -> str:
                return "Bad"


def test_base_pipeline_frozen_override_raises() -> None:
    """Test that overriding frozen=True in BasePipeline subclass raises TypeError."""
    with pytest.raises(TypeError, match="must not override frozen=True"):

        class TestConfig(BasePipelineSettings):
            pipeline_type = "test"

            def pipeline_label(self) -> str:
                return "Test"

        class TestResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> JsonObject:
                return {"success": self.success}

        class BadPipeline(BasePipeline):
            pipeline_type = "bad"
            description = "test"
            model_config = ConfigDict(frozen=False)

            @classmethod
            def config_model(cls) -> type[TestConfig]:
                return TestConfig

            @classmethod
            def result_model(cls) -> type[TestResult]:
                return TestResult

            def run(self) -> TestResult:
                return TestResult()

            def _build_components(self) -> None:
                pass


def test_valid_subclasses_work() -> None:
    """Test that valid subclasses without frozen override work correctly."""

    class GoodConfig(BasePipelineSettings):
        pipeline_type = "good"

        def pipeline_label(self) -> str:
            return "Good"

    class GoodResult(BasePipelineResult):
        pipeline_type = "good"

        def summary_fields(self) -> JsonObject:
            return {"success": self.success}

    class GoodPipeline(BasePipeline):
        pipeline_type = "good"
        description = "test pipeline"

        @classmethod
        def config_model(cls) -> type[GoodConfig]:
            return GoodConfig

        @classmethod
        def result_model(cls) -> type[GoodResult]:
            return GoodResult

        def run(self) -> GoodResult:
            return GoodResult()

        def _build_components(self) -> None:
            pass

    # Should not raise
    assert GoodConfig.model_config.get("frozen") is True
    assert GoodResult.model_config.get("frozen") is True
    assert GoodPipeline.model_config.get("frozen") is True
