# tests/pipelines/test_base.py
"""Unit tests for sec_nlp.pipelines.base module."""

import inspect
from pathlib import Path

import pytest
from langchain_core.runnables import Runnable

from sec_nlp.pipelines import (
    BasePipeline,
    BasePipelineResult,
    BasePipelineSettings,
)
from sec_nlp.types import JsonValue


class _ConcreteResult(BasePipelineResult):
    pipeline_type = "concrete"

    def summary_fields(self) -> dict[str, JsonValue]:
        return {"success": self.success}


class _ConcreteConfig(BasePipelineSettings):
    pipeline_type = "concrete"

    def pipeline_label(self) -> str:
        return "Concrete"


class TestBasePipelineResult:
    """Tests for BasePipelineResult class."""

    def test_base_result_is_abstract(self) -> None:
        """BasePipelineResult cannot be instantiated directly."""
        assert inspect.isabstract(BasePipelineResult)

    def test_concrete_result_initialization(self) -> None:
        """Test that a concrete BasePipelineResult subclass initializes with defaults."""
        result = _ConcreteResult()

        assert result.success is True
        assert result.outputs == []
        assert result.metadata == {}
        assert result.error is None
        assert result.raw_output is None

    def test_concrete_result_with_custom_values(self) -> None:
        """Test BasePipelineResult subclass with custom values."""
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


class TestBasePipelineSettings:
    """Tests for BasePipelineSettings class."""

    def test_base_config_is_abstract(self) -> None:
        """BasePipelineSettings cannot be instantiated directly."""
        assert inspect.isabstract(BasePipelineSettings)

    def test_base_config_default_values(self) -> None:
        """Test BasePipelineSettings default values."""
        config = _ConcreteConfig()

        assert config.verbose is False
        assert config.dry_run is True
        assert config.log_format == "simple"
        assert config.log_file is None

    def test_base_config_with_custom_values(self) -> None:
        """Test BasePipelineSettings with custom values."""
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

    def test_base_config_log_file_creates_parent_dir(
        self,
        tmp_path: Path,
        temp_pipeline_config: BasePipelineSettings,
    ) -> None:
        """Test that setup_paths creates log_file parent directory."""
        log_file = tmp_path / "logs" / "nested" / "test.log"

        config = _ConcreteConfig(
            log_file=log_file,
            out_path=temp_pipeline_config.out_path,
            dl_path=temp_pipeline_config.dl_path,
        )
        config.setup_paths()

        assert config.log_file == log_file
        assert log_file.parent.exists()

    def test_setup_paths_does_not_precreate_symbol_output_dirs(
        self,
        tmp_path: Path,
    ) -> None:
        """setup_paths should not create symbol dirs until output write time."""
        config = _ConcreteConfig(
            symbols=["ABC"],
            out_path=tmp_path / "outputs",
            dl_path=tmp_path / "downloads",
        )
        config.setup_paths()

        symbol_dir = (
            config.out_path
            / config.run_path_component()
            / config.pipeline_type
            / "ABC"
        )
        assert symbol_dir.exists() is False

    def test_complete_run_prunes_empty_symbol_and_run_dirs(
        self,
        tmp_path: Path,
    ) -> None:
        """complete_run should remove empty symbol and run directories."""
        config = _ConcreteConfig(
            symbols=["ABC"],
            out_path=tmp_path / "outputs",
            dl_path=tmp_path / "downloads",
        )
        config.setup_paths()
        symbol_dir = config.get_symbol_output_dir("ABC")
        assert symbol_dir.exists() is True

        config.complete_run(success=True)

        pipeline_dir = (
            config.out_path / config.run_path_component() / config.pipeline_type
        )
        run_dir = config.out_path / config.run_path_component()
        assert symbol_dir.exists() is False
        assert pipeline_dir.exists() is False
        assert run_dir.exists() is False


class TestBasePipeline:
    """Tests for BasePipeline class."""

    def test_base_pipeline_is_abstract(self) -> None:
        """Test that BasePipeline cannot be instantiated directly."""
        assert inspect.isabstract(BasePipeline)

    def test_concrete_pipeline_can_be_instantiated(self) -> None:
        """Test that concrete pipeline subclass can be instantiated."""

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "concrete"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"
            custom_output: str = "result"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

    def test_pipeline_is_runnable_and_invoke_calls_run(self) -> None:
        """Test BasePipeline subclasses satisfy Runnable.invoke semantics."""

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

        pipeline = ConcretePipeline(config=ConcreteConfig())
        assert isinstance(pipeline, Runnable)

        result = pipeline.invoke()

        assert run_called is True
        assert isinstance(result, ConcreteResult)

    def test_pipeline_invoke_rejects_non_null_input(self) -> None:
        """Test invoke() rejects non-null input for pipeline runnables."""

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

        pipeline = ConcretePipeline(config=ConcreteConfig())
        with pytest.raises(ValueError, match="does not accept input"):
            pipeline.invoke(input="invalid")

    def test_pipeline_requires_config_model_method(self) -> None:
        """Test that pipeline raises TypeError if config_model() is missing."""

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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

        class ConcreteResult(BasePipelineResult):
            pipeline_type = "test"

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success}

        class ConcreteConfig(BasePipelineSettings):
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
