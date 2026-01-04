# tests/pipelines/test_base.py
"""Unit tests for sec_nlp.pipelines.base module."""

import inspect
from pathlib import Path

import pytest

from sec_nlp.pipelines import (
    BaseConfig,
    BasePipeline,
    BaseResult,
)
from sec_nlp.types import JsonValue


class _ConcreteResult(BaseResult):
    pipeline_type = "concrete"

    def summary_fields(self) -> dict[str, JsonValue]:
        return {"success": self.success}


class _ConcreteConfig(BaseConfig):
    pipeline_type = "concrete"

    def pipeline_label(self) -> str:
        return "Concrete"


class TestBaseResult:
    """Tests for BaseResult class."""

    def test_base_result_is_abstract(self) -> None:
        """BaseResult cannot be instantiated directly."""
        assert inspect.isabstract(BaseResult)

    def test_concrete_result_initialization(self) -> None:
        """Test that a concrete BaseResult subclass initializes with defaults."""
        result = _ConcreteResult()

        assert result.success is True
        assert result.outputs == []
        assert result.metadata == {}
        assert result.error is None
        assert result.raw_output is None

    def test_concrete_result_with_custom_values(self) -> None:
        """Test BaseResult subclass with custom values."""
        outputs = [Path("/tmp/output1.txt"), Path("/tmp/output2.txt")]
        metadata = {"key": "value", "count": 42}

        result = _ConcreteResult(
            success=False,
            outputs=outputs,
            metadata=metadata,
            error="Something went wrong",
            raw_output="Raw data here",
        )

        assert result.success is False
        assert result.outputs == outputs
        assert result.metadata == metadata
        assert result.error == "Something went wrong"
        assert result.raw_output == "Raw data here"

    def test_base_result_is_success_when_success_true(self) -> None:
        """Test is_success returns True when success=True and no error."""
        result = _ConcreteResult(success=True, error=None)

        assert result.is_success() is True

    def test_base_result_is_success_when_success_false(self) -> None:
        """Test is_success returns False when success=False."""
        result = _ConcreteResult(success=False)

        assert result.is_success() is False

    def test_base_result_is_success_when_error_present(self) -> None:
        """Test is_success returns False when error is present."""
        result = _ConcreteResult(success=True, error="Some error")

        assert result.is_success() is False


class TestBaseConfig:
    """Tests for BaseConfig class."""

    def test_base_config_is_abstract(self) -> None:
        """BaseConfig cannot be instantiated directly."""
        assert inspect.isabstract(BaseConfig)

    def test_base_config_default_values(self) -> None:
        """Test BaseConfig default values."""
        config = _ConcreteConfig()

        assert config.verbose is False
        assert config.dry_run is True
        assert config.log_format == "simple"
        assert config.log_file is None

    def test_base_config_with_custom_values(self) -> None:
        """Test BaseConfig with custom values."""
        log_file = Path("/tmp/test.log")

        config = _ConcreteConfig(
            verbose=True,
            dry_run=False,
            log_format="json",
            log_file=log_file,
        )

        assert config.verbose is True
        assert config.dry_run is False
        assert config.log_format == "json"
        assert config.log_file == log_file

    def test_base_config_get_log_level_verbose(self) -> None:
        """Test get_log_level returns DEBUG when verbose=True."""
        config = _ConcreteConfig(verbose=True)

        assert config.get_log_level() == "DEBUG"

    def test_base_config_get_log_level_not_verbose(self) -> None:
        """Test get_log_level returns INFO when verbose=False."""
        config = _ConcreteConfig(verbose=False)

        assert config.get_log_level() == "INFO"

    def test_base_config_log_file_creates_parent_dir(self) -> None:
        """Test that setup_paths creates log_file parent directory."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "logs" / "nested" / "test.log"

            config = _ConcreteConfig(log_file=log_file)
            config.setup_paths()

            assert config.log_file == log_file
            assert log_file.parent.exists()


class TestBasePipeline:
    """Tests for BasePipeline class."""

    def test_base_pipeline_is_abstract(self) -> None:
        """Test that BasePipeline cannot be instantiated directly."""
        assert inspect.isabstract(BasePipeline)

    def test_concrete_pipeline_can_be_instantiated(self) -> None:
        """Test that concrete pipeline subclass can be instantiated."""

        class ConcreteResult(BaseResult):
            pipeline_type = "concrete"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BaseConfig):
            pipeline_type = "concrete"

            def pipeline_label(self) -> str:
                return "Concrete"

        class ConcretePipeline(BasePipeline):
            pipeline_type = "concrete"
            description = "A concrete pipeline for testing"

            @classmethod
            def config_model(cls) -> type[ConcreteConfig]:
                return ConcreteConfig

            @classmethod
            def result_model(cls) -> type[ConcreteResult]:
                return ConcreteResult

            def run(self) -> ConcreteResult:
                return ConcreteResult()

            def _build_components(self) -> None:
                pass

        config = ConcreteConfig()
        pipeline = ConcretePipeline(config=config)

        assert pipeline.config == config
        assert pipeline.pipeline_type == "concrete"

    def test_pipeline_run_method_must_be_implemented(self) -> None:
        """Test that run() method must be implemented."""

        class ConcreteResult(BaseResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BaseConfig):
            pipeline_type = "test"

            def pipeline_label(self) -> str:
                return "Test"

        class IncompletePipeline(BasePipeline):
            pipeline_type = "test"
            description = "Incomplete"

            @classmethod
            def config_model(cls) -> type[ConcreteConfig]:
                return ConcreteConfig

            @classmethod
            def result_model(cls) -> type[ConcreteResult]:
                return ConcreteResult

            def _build_components(self) -> None:
                pass

        assert inspect.isabstract(IncompletePipeline)

    def test_pipeline_get_config_model(self) -> None:
        """Test get_config_model class method."""

        class ConcreteResult(BaseResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BaseConfig):
            pipeline_type = "test"
            custom_field: str = "test"

            def pipeline_label(self) -> str:
                return "Test"

        class ConcretePipeline(BasePipeline):
            pipeline_type = "test"
            description = "Test"

            @classmethod
            def config_model(cls) -> type[ConcreteConfig]:
                return ConcreteConfig

            @classmethod
            def result_model(cls) -> type[ConcreteResult]:
                return ConcreteResult

            def run(self) -> ConcreteResult:
                return ConcreteResult()

            def _build_components(self) -> None:
                pass

        config_model = ConcretePipeline.get_config_model()

        assert config_model is ConcreteConfig

    def test_pipeline_get_result_model(self) -> None:
        """Test get_result_model class method."""

        class ConcreteResult(BaseResult):
            pipeline_type = "test"
            custom_output: str = "result"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BaseConfig):
            pipeline_type = "test"

            def pipeline_label(self) -> str:
                return "Test"

        class ConcretePipeline(BasePipeline):
            pipeline_type = "test"
            description = "Test"

            @classmethod
            def config_model(cls) -> type[ConcreteConfig]:
                return ConcreteConfig

            @classmethod
            def result_model(cls) -> type[ConcreteResult]:
                return ConcreteResult

            def run(self) -> ConcreteResult:
                return ConcreteResult()

            def _build_components(self) -> None:
                pass

        result_model = ConcretePipeline.get_result_model()

        assert result_model is ConcreteResult

    def test_pipeline_model_post_init_called(self) -> None:
        """Test that model_post_init is called during initialization."""

        class ConcreteResult(BaseResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BaseConfig):
            pipeline_type = "test"

            def pipeline_label(self) -> str:
                return "Test"

        build_called = False

        class ConcretePipeline(BasePipeline):
            pipeline_type = "test"
            description = "Test"

            @classmethod
            def config_model(cls) -> type[ConcreteConfig]:
                return ConcreteConfig

            @classmethod
            def result_model(cls) -> type[ConcreteResult]:
                return ConcreteResult

            def run(self) -> ConcreteResult:
                return ConcreteResult()

            def _build_components(self) -> None:
                nonlocal build_called
                build_called = True

        config = ConcreteConfig()
        _pipeline = ConcretePipeline(config=config)

        assert build_called is True

    def test_pipeline_cli_cmd_calls_run(self) -> None:
        """Test that cli_cmd() calls run()."""

        class ConcreteResult(BaseResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BaseConfig):
            pipeline_type = "test"

            def pipeline_label(self) -> str:
                return "Test"

        run_called = False

        class ConcretePipeline(BasePipeline):
            pipeline_type = "test"
            description = "Test"

            @classmethod
            def config_model(cls) -> type[ConcreteConfig]:
                return ConcreteConfig

            @classmethod
            def result_model(cls) -> type[ConcreteResult]:
                return ConcreteResult

            def run(self) -> ConcreteResult:
                nonlocal run_called
                run_called = True
                return ConcreteResult()

            def _build_components(self) -> None:
                pass

        config = ConcreteConfig()
        pipeline = ConcretePipeline(config=config)
        result = pipeline.cli_cmd()

        assert run_called is True
        assert isinstance(result, ConcreteResult)

    def test_pipeline_requires_config_model_method(self) -> None:
        """Test that pipeline raises TypeError if config_model() is missing."""

        class ConcreteResult(BaseResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BaseConfig):
            pipeline_type = "test"

            def pipeline_label(self) -> str:
                return "Test"

        class BadPipeline(BasePipeline):
            pipeline_type = "test"
            description = "Bad"

            @classmethod
            def result_model(cls) -> type[ConcreteResult]:
                return ConcreteResult

            def run(self) -> ConcreteResult:
                return ConcreteResult()

            def _build_components(self) -> None:
                pass

        with pytest.raises(TypeError, match=r"abstract class BadPipeline"):
            BadPipeline(config=ConcreteConfig())

    def test_pipeline_requires_result_model_method(self) -> None:
        """Test that pipeline raises TypeError if result_model() is missing."""

        class ConcreteResult(BaseResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BaseConfig):
            pipeline_type = "test"

            def pipeline_label(self) -> str:
                return "Test"

        class BadPipeline(BasePipeline):
            pipeline_type = "test"
            description = "Bad"

            @classmethod
            def config_model(cls) -> type[ConcreteConfig]:
                return ConcreteConfig

            def run(self) -> ConcreteResult:
                return ConcreteResult()

            def _build_components(self) -> None:
                pass

        with pytest.raises(TypeError, match=r"abstract class BadPipeline"):
            BadPipeline(config=ConcreteConfig())
