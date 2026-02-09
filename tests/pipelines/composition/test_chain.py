# tests/pipelines/composition/test_chain.py
"""Tests for pipeline composition framework."""

from pathlib import Path
from typing import ClassVar, Literal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ConfigDict

from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.base.pipeline import BasePipeline
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.pipelines.composition import (
    ChainResult,
    PipelineChain,
    PipelineStage,
    StageOutput,
    create_stage,
    has_metadata_key,
    has_outputs,
    is_successful,
)
from sec_nlp.types import JsonObject


# Test fixtures - minimal pipeline implementations for testing
class _TestConfig(BasePipelineSettings):
    """Minimal test config."""

    pipeline_type: ClassVar[Literal["test"]] = "test"

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    test_value: str = "default"

    def pipeline_label(self) -> str:
        return "Test Pipeline"


class _TestResult(BasePipelineResult):
    """Minimal test result."""

    pipeline_type: ClassVar[Literal["test"]] = "test"

    def summary_fields(self) -> JsonObject:
        return self.base_summary_fields()


class _TestPipeline(BasePipeline):
    """Minimal test pipeline."""

    pipeline_type: ClassVar[Literal["test"]] = "test"
    description: ClassVar[str] = "Test pipeline"

    config: _TestConfig

    @classmethod
    def config_model(cls) -> type[_TestConfig]:
        return _TestConfig

    @classmethod
    def result_model(cls) -> type[_TestResult]:
        return _TestResult

    def _build_components(self) -> None:
        pass

    def run(self) -> _TestResult:
        return _TestResult(
            success=True,
            outputs=[Path("/test/output.json")],
            metadata={"test_value": self.config.test_value},
        )


class _FailingPipeline(BasePipeline):
    """Pipeline that always fails."""

    pipeline_type: ClassVar[Literal["failing"]] = "failing"
    description: ClassVar[str] = "Failing pipeline"

    config: _TestConfig

    @classmethod
    def config_model(cls) -> type[_TestConfig]:
        return _TestConfig

    @classmethod
    def result_model(cls) -> type[_TestResult]:
        return _TestResult

    def _build_components(self) -> None:
        pass

    def run(self) -> _TestResult:
        return _TestResult(
            success=False,
            error="Intentional failure",
        )


class _ExceptionPipeline(BasePipeline):
    """Pipeline that raises an exception."""

    pipeline_type: ClassVar[Literal["exception"]] = "exception"
    description: ClassVar[str] = "Exception pipeline"

    config: _TestConfig

    @classmethod
    def config_model(cls) -> type[_TestConfig]:
        return _TestConfig

    @classmethod
    def result_model(cls) -> type[_TestResult]:
        return _TestResult

    def _build_components(self) -> None:
        pass

    def run(self) -> _TestResult:
        raise ValueError("Intentional exception")


class TestStageOutput:
    """Tests for StageOutput."""

    def test_create_from_result(self) -> None:
        """Test creating StageOutput from pipeline result."""
        result = _TestResult(
            success=True,
            outputs=[Path("/test/output.json")],
            metadata={"key": "value"},
        )

        output = StageOutput.from_result(result)

        assert output.success is True
        assert output.outputs == [Path("/test/output.json")]
        assert output.metadata == {"key": "value"}
        assert output.error is None


class TestPipelineStage:
    """Tests for PipelineStage."""

    def test_create_stage(self) -> None:
        """Test creating a pipeline stage."""
        config = _TestConfig()
        stage = create_stage(
            name="test_stage",
            pipeline_cls=_TestPipeline,
            config=config,
        )

        assert stage.name == "test_stage"
        assert stage.pipeline_cls == _TestPipeline
        assert stage.config == config
        assert stage.skip_on_failure is False
        assert stage.condition is None

    def test_should_run_first_stage(self) -> None:
        """Test that first stage always runs by default."""
        config = _TestConfig()
        stage = create_stage("test", _TestPipeline, config)

        assert stage.should_run(None) is True

    def test_should_run_after_success(self) -> None:
        """Test that stage runs after successful previous stage."""
        config = _TestConfig()
        stage = create_stage("test", _TestPipeline, config)

        previous = StageOutput(success=True)
        assert stage.should_run(previous) is True

    def test_should_run_after_failure_no_skip(self) -> None:
        """Test that stage runs after failure when skip_on_failure=False."""
        config = _TestConfig()
        stage = create_stage(
            "test", _TestPipeline, config, skip_on_failure=False
        )

        previous = StageOutput(success=False)
        assert stage.should_run(previous) is True

    def test_should_run_after_failure_with_skip(self) -> None:
        """Test that stage skips after failure when skip_on_failure=True."""
        config = _TestConfig()
        stage = create_stage(
            "test", _TestPipeline, config, skip_on_failure=True
        )

        previous = StageOutput(success=False)
        assert stage.should_run(previous) is False

    def test_should_run_with_condition(self) -> None:
        """Test custom condition function."""
        config = _TestConfig()
        stage = create_stage(
            "test",
            _TestPipeline,
            config,
            condition=lambda out: out is not None and len(out.outputs) > 0,
        )

        # No outputs - should not run
        previous_no_outputs = StageOutput(success=True, outputs=[])
        assert stage.should_run(previous_no_outputs) is False

        # Has outputs - should run
        previous_with_outputs = StageOutput(
            success=True, outputs=[Path("/test/output.json")]
        )
        assert stage.should_run(previous_with_outputs) is True

    def test_run_stage(self) -> None:
        """Test running a pipeline stage."""
        config = _TestConfig(test_value="stage_test")
        stage = create_stage("test", _TestPipeline, config)

        output = stage.run()

        assert output.success is True
        assert len(output.outputs) == 1
        assert output.metadata.get("test_value") == "stage_test"


class TestConditionFunctions:
    """Tests for condition helper functions."""

    def test_has_outputs_true(self) -> None:
        """Test has_outputs when outputs exist."""
        output = StageOutput(success=True, outputs=[Path("/test/output.json")])
        assert has_outputs(output) is True

    def test_has_outputs_false(self) -> None:
        """Test has_outputs when no outputs."""
        output = StageOutput(success=True, outputs=[])
        assert has_outputs(output) is False

    def test_has_outputs_none(self) -> None:
        """Test has_outputs for first stage (None)."""
        assert has_outputs(None) is True

    def test_has_metadata_key_true(self) -> None:
        """Test has_metadata_key when key exists."""
        output = StageOutput(success=True, metadata={"target_key": "value"})
        condition = has_metadata_key("target_key")
        assert condition(output) is True

    def test_has_metadata_key_false(self) -> None:
        """Test has_metadata_key when key missing."""
        output = StageOutput(success=True, metadata={"other_key": "value"})
        condition = has_metadata_key("target_key")
        assert condition(output) is False

    def test_is_successful_true(self) -> None:
        """Test is_successful when successful."""
        output = StageOutput(success=True)
        assert is_successful(output) is True

    def test_is_successful_false(self) -> None:
        """Test is_successful when failed."""
        output = StageOutput(success=False)
        assert is_successful(output) is False


class TestPipelineChain:
    """Tests for PipelineChain."""

    def test_create_empty_chain(self) -> None:
        """Test creating an empty chain."""
        chain = PipelineChain(name="test_chain")

        assert chain.name == "test_chain"
        assert len(chain) == 0
        assert chain.stages == []

    def test_add_stage_fluent(self) -> None:
        """Test fluent API for adding stages."""
        config = _TestConfig()
        chain = (
            PipelineChain(name="test_chain")
            .add_stage("stage1", _TestPipeline, config)
            .add_stage("stage2", _TestPipeline, config)
        )

        assert len(chain) == 2
        assert chain.stages[0].name == "stage1"
        assert chain.stages[1].name == "stage2"

    def test_run_single_stage_success(self) -> None:
        """Test running a chain with a single successful stage."""
        config = _TestConfig(test_value="single_stage")
        chain = PipelineChain(name="test", verbose=False).add_stage(
            "stage1", _TestPipeline, config
        )

        result = chain.run()

        assert result.success is True
        assert len(result.stage_results) == 1
        assert result.stage_results[0].stage_name == "stage1"
        assert result.stage_results[0].output.success is True
        assert len(result.outputs) == 1

    def test_run_multiple_stages_success(self) -> None:
        """Test running a chain with multiple successful stages."""
        config1 = _TestConfig(test_value="stage1")
        config2 = _TestConfig(test_value="stage2")
        chain = (
            PipelineChain(name="multi_stage", verbose=False)
            .add_stage("stage1", _TestPipeline, config1)
            .add_stage("stage2", _TestPipeline, config2)
        )

        result = chain.run()

        assert result.success is True
        assert len(result.stage_results) == 2
        assert all(r.output.success for r in result.stage_results)
        assert len(result.outputs) == 2  # One from each stage

    def test_run_with_failure_stops_chain(self) -> None:
        """Test that chain stops on failure when stop_on_failure=True."""
        config = _TestConfig()
        chain = (
            PipelineChain(
                name="failing_chain", verbose=False, stop_on_failure=True
            )
            .add_stage("stage1", _FailingPipeline, config)
            .add_stage("stage2", _TestPipeline, config)
        )

        result = chain.run()

        assert result.success is False
        assert len(result.stage_results) == 2
        assert result.stage_results[0].output.success is False
        assert result.stage_results[1].skipped is True

    def test_run_with_failure_continues(self) -> None:
        """Test that chain continues after failure when stop_on_failure=False."""
        config = _TestConfig()
        chain = (
            PipelineChain(
                name="continue_chain", verbose=False, stop_on_failure=False
            )
            .add_stage("stage1", _FailingPipeline, config)
            .add_stage("stage2", _TestPipeline, config)
        )

        result = chain.run()

        assert result.success is False  # Overall failed
        assert len(result.stage_results) == 2
        assert result.stage_results[0].output.success is False
        assert result.stage_results[1].skipped is False
        assert result.stage_results[1].output.success is True

    def test_run_with_exception(self) -> None:
        """Test handling of exception in pipeline."""
        config = _TestConfig()
        chain = PipelineChain(name="exception_chain", verbose=False).add_stage(
            "stage1", _ExceptionPipeline, config
        )

        result = chain.run()

        assert result.success is False
        assert len(result.stage_results) == 1
        assert result.stage_results[0].output.success is False
        assert "ValueError" in (result.stage_results[0].output.error or "")

    def test_run_with_condition_skip(self) -> None:
        """Test that stage is skipped when condition returns False."""
        config = _TestConfig()
        chain = (
            PipelineChain(name="conditional", verbose=False)
            .add_stage("stage1", _TestPipeline, config)
            .add_stage(
                "stage2",
                _TestPipeline,
                config,
                condition=lambda out: False,  # Always skip
            )
        )

        result = chain.run()

        assert result.success is True
        assert len(result.stage_results) == 2
        assert result.stage_results[0].skipped is False
        assert result.stage_results[1].skipped is True

    def test_chain_result_summary_fields(self) -> None:
        """Test ChainResult summary fields."""
        config = _TestConfig()
        chain = (
            PipelineChain(name="summary_test", verbose=False)
            .add_stage("stage1", _TestPipeline, config)
            .add_stage("stage2", _TestPipeline, config)
        )

        result = chain.run()
        summary = result.summary_fields()

        assert summary["pipeline"] == "chain"
        assert summary["success"] is True
        assert summary["stages_total"] == 2
        assert summary["stages_successful"] == 2
        assert summary["stages_skipped"] == 0
        assert summary["stages_failed"] == 0
        assert "duration_seconds" in summary

    def test_chain_repr(self) -> None:
        """Test chain string representation."""
        config = _TestConfig()
        chain = (
            PipelineChain(name="repr_test")
            .add_stage("stage1", _TestPipeline, config)
            .add_stage("stage2", _TestPipeline, config)
        )

        repr_str = repr(chain)
        assert "repr_test" in repr_str
        assert "stage1" in repr_str
        assert "stage2" in repr_str

    def test_chain_timing(self) -> None:
        """Test that timing information is captured."""
        config = _TestConfig()
        chain = PipelineChain(name="timing_test", verbose=False).add_stage(
            "stage1", _TestPipeline, config
        )

        result = chain.run()

        assert result.total_duration_seconds > 0
        assert result.stage_results[0].duration_seconds > 0


class TestChainResult:
    """Tests for ChainResult model."""

    def test_chain_result_is_success(self) -> None:
        """Test ChainResult.is_success method."""
        result = ChainResult(
            success=True,
            stage_results=[],
            total_duration_seconds=1.0,
        )
        assert result.is_success() is True

    def test_chain_result_print_summary(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ChainResult print_summary method."""
        result = ChainResult(
            success=True,
            outputs=[Path("/test/output.json")],
            stage_results=[],
            total_duration_seconds=1.0,
        )
        result.print_summary()

        captured = capsys.readouterr()
        assert "Success" in captured.out
        assert "chain" in captured.out
