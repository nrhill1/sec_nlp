# tests/pipelines/test_base_edge_cases.py
"""Comprehensive edge case tests for BasePipeline to prevent undefined behavior."""

from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import pytest

from sec_nlp.pipelines import (
    BaseConfig,
    BasePipeline,
    BaseResult,
)
from sec_nlp.types import JsonObject


class EdgeCaseConfig(BaseConfig):
    """Config for edge case testing."""

    pipeline_type: ClassVar[str] = "edge_case"
    test_value: str = "default"

    def pipeline_label(self) -> str:
        return "Edge Case"


class EdgeCaseResult(BaseResult):
    """Result for edge case testing."""

    pipeline_type: ClassVar[str] = "edge_case"

    def summary_fields(self) -> JsonObject:
        return {"success": self.success}


class EdgeCasePipeline(BasePipeline):
    """Concrete pipeline for edge case testing."""

    pipeline_type: ClassVar[str] = "edge_case"
    description: ClassVar[str] = "Edge case test pipeline"

    @classmethod
    def config_model(cls) -> type[EdgeCaseConfig]:
        return EdgeCaseConfig

    @classmethod
    def result_model(cls) -> type[EdgeCaseResult]:
        return EdgeCaseResult

    def run(self) -> EdgeCaseResult:
        return EdgeCaseResult(success=True)

    def _build_components(self) -> None:
        pass


class TestBaseResultEdgeCases:
    """Edge case tests for BaseResult."""

    def test_result_with_empty_outputs(self) -> None:
        """Test result with explicitly empty outputs list."""
        result = EdgeCaseResult(outputs=[])
        assert result.outputs == []
        assert result.is_success()

    def test_result_with_none_metadata(self) -> None:
        """Test result initialization handles None metadata gracefully."""
        result = EdgeCaseResult(metadata={})
        assert result.metadata == {}

    def test_result_with_large_metadata(self) -> None:
        """Test result can handle large metadata dictionaries."""
        large_metadata = {f"key_{i}": f"value_{i}" for i in range(1000)}
        result = EdgeCaseResult(metadata=large_metadata)
        assert len(result.metadata) == 1000
        assert result.metadata["key_500"] == "value_500"

    def test_result_with_nested_metadata(self) -> None:
        """Test result with deeply nested metadata."""
        nested = {"level1": {"level2": {"level3": {"data": "deep"}}}}
        result = EdgeCaseResult(metadata=nested)
        level1 = result.metadata.get("level1")
        assert isinstance(level1, dict)
        level2 = level1["level2"]
        assert isinstance(level2, dict)
        level3 = level2["level3"]
        assert isinstance(level3, dict)
        assert level3["data"] == "deep"

    def test_result_with_empty_error_string(self) -> None:
        """Test result with empty error string is treated as no error."""
        result = EdgeCaseResult(error="")
        # Empty string is still truthy for is_success check
        assert result.is_success()

    def test_result_with_whitespace_error(self) -> None:
        """Test result with whitespace-only"""
        result = EdgeCaseResult(error="   ")
        assert not result.is_success()

    def test_result_with_very_long_raw_output(self) -> None:
        """Test result can handle very long raw output."""
        long_output: str = "x" * 1_000_000  # 1MB of data
        result: BaseResult = EdgeCaseResult(raw_output=long_output)
        assert result.raw_output is not None
        assert len(result.raw_output) == 1_000_000

    def test_result_with_special_characters_in_error(self) -> None:
        """Test result handles special characters in error messages."""
        special_chars = "Error: \n\t\r\0 \x00 unicode: 🚨"
        result = EdgeCaseResult(error=special_chars)
        assert result.error == special_chars
        assert not result.is_success()

    def test_result_outputs_with_nonexistent_paths(self) -> None:
        """Test result accepts nonexistent file paths."""
        fake_paths = [
            Path("/nonexistent/file1.txt"),
            Path("/fake/path/file2.json"),
        ]
        result = EdgeCaseResult(outputs=fake_paths)
        assert len(result.outputs) == 2
        assert result.outputs[0] == fake_paths[0]

    def test_result_success_false_error_none(self) -> None:
        """Test result with success=False but no error message."""
        result = EdgeCaseResult(success=False, error=None)
        assert not result.is_success()
        assert result.error is None

    def test_result_success_true_with_error(self) -> None:
        """Test conflicting success=True with error present."""
        result = EdgeCaseResult(success=True, error="Something wrong")
        # is_success should return False when error is present
        assert not result.is_success()

    def test_result_repr_without_pipeline_type(self) -> None:
        """Test __repr__ when pipeline_type is not set."""
        result = EdgeCaseResult()
        repr_str = repr(result)
        assert "EdgeCaseResult" in repr_str


class TestBaseConfigEdgeCases:
    """Edge case tests for BaseConfig."""

    def test_config_log_file_under_tmp_path(
        self,
        tmp_path: Path,
        temp_pipeline_config: BaseConfig,
    ) -> None:
        """Test that setup_paths creates log_file parent directory."""
        relative_path = Path("logs/test.log")
        log_file = tmp_path / relative_path
        config = EdgeCaseConfig(
            log_file=log_file,
            out_path=temp_pipeline_config.out_path,
            dl_path=temp_pipeline_config.dl_path,
        )
        assert config.log_file == log_file
        # Parent directory should be created
        config.setup_paths()
        assert log_file.parent.exists()

    def test_config_log_file_with_symlink(self) -> None:
        """Test config with symlinked log file path."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = Path(tmpdir) / "real"
            real_dir.mkdir()
            link_dir = Path(tmpdir) / "link"
            link_dir.symlink_to(real_dir)

            log_file = link_dir / "test.log"
            config = EdgeCaseConfig(log_file=log_file)
            assert config.log_file == log_file

    def test_config_repr_without_pipeline_type(self) -> None:
        """Test __repr__ when pipeline_type is not set."""
        config = EdgeCaseConfig()
        repr_str = repr(config)
        assert "EdgeCaseConfig" in repr_str


class TestBasePipelineEdgeCases:
    """Edge case tests for BasePipeline."""

    def test_pipeline_get_config_model_missing_method(self) -> None:
        """Test get_config_model does not infer when config_model() is missing."""

        class MissingMethodPipeline(BasePipeline):
            pipeline_type: ClassVar[str] = "missing"
            description: ClassVar[str] = "Missing"

            @classmethod
            def result_model(cls) -> type[EdgeCaseResult]:
                return EdgeCaseResult

            def run(self) -> EdgeCaseResult:
                return EdgeCaseResult()

            def _build_components(self) -> None:
                pass

        with pytest.raises(NotImplementedError):
            MissingMethodPipeline.get_config_model()

    def test_pipeline_get_result_model_requires_method(self) -> None:
        """Test get_result_model does not infer from run() annotation."""

        class AnnotationPipeline(BasePipeline):
            pipeline_type: ClassVar[str] = "annotation"
            description: ClassVar[str] = "Annotation"

            @classmethod
            def config_model(cls) -> type[EdgeCaseConfig]:
                return EdgeCaseConfig

            def run(self) -> EdgeCaseResult:
                return EdgeCaseResult()

            def _build_components(self) -> None:
                pass

        with pytest.raises(NotImplementedError):
            AnnotationPipeline.get_result_model()

    def test_pipeline_requires_llm_without_config(self) -> None:
        """Test pipeline warns when requires_llm but no LLM config."""

        class LLMPipeline(BasePipeline):
            pipeline_type: ClassVar[str] = "llm"
            description: ClassVar[str] = "LLM"
            requires_llm: ClassVar[bool] = True

            @classmethod
            def config_model(cls) -> type[EdgeCaseConfig]:
                return EdgeCaseConfig

            @classmethod
            def result_model(cls) -> type[EdgeCaseResult]:
                return EdgeCaseResult

            def run(self) -> EdgeCaseResult:
                return EdgeCaseResult()

            def _build_components(self) -> None:
                pass

        config = EdgeCaseConfig()

        with patch("sec_nlp.pipelines.base.pipeline.logger") as mock_logger:
            _pipeline = LLMPipeline(config=config)
            mock_logger.warning.assert_called()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "LLM" in warning_msg

    def test_pipeline_requires_vector_db_without_config(self) -> None:
        """Test pipeline warns when requires_vector_db but no vector DB config."""

        class VectorPipeline(BasePipeline):
            pipeline_type: ClassVar[str] = "vector"
            description: ClassVar[str] = "Vector"
            requires_vector_db: ClassVar[bool] = True

            @classmethod
            def config_model(cls) -> type[EdgeCaseConfig]:
                return EdgeCaseConfig

            @classmethod
            def result_model(cls) -> type[EdgeCaseResult]:
                return EdgeCaseResult

            def run(self) -> EdgeCaseResult:
                return EdgeCaseResult()

            def _build_components(self) -> None:
                pass

        config = EdgeCaseConfig()

        with patch("sec_nlp.pipelines.base.pipeline.logger") as mock_logger:
            _pipeline = VectorPipeline(config=config)
            mock_logger.warning.assert_called()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "vector DB" in warning_msg

    def test_pipeline_build_components_exception(self) -> None:
        """Test pipeline handles exceptions in _build_components."""

        class FailingBuildPipeline(BasePipeline):
            pipeline_type: ClassVar[str] = "failing"
            description: ClassVar[str] = "Failing"

            @classmethod
            def config_model(cls) -> type[EdgeCaseConfig]:
                return EdgeCaseConfig

            @classmethod
            def result_model(cls) -> type[EdgeCaseResult]:
                return EdgeCaseResult

            def run(self) -> EdgeCaseResult:
                return EdgeCaseResult()

            def _build_components(self) -> None:
                raise RuntimeError("Component build failed")

        config = EdgeCaseConfig()

        with pytest.raises(RuntimeError, match="Component build failed"):
            FailingBuildPipeline(config=config)

    def test_pipeline_validate_requirements_exception(self) -> None:
        """Test pipeline handles exceptions in _validate_requirements."""

        class FailingValidatePipeline(BasePipeline):
            pipeline_type: ClassVar[str] = "failing_validate"
            description: ClassVar[str] = "Failing Validate"

            @classmethod
            def config_model(cls) -> type[EdgeCaseConfig]:
                return EdgeCaseConfig

            @classmethod
            def result_model(cls) -> type[EdgeCaseResult]:
                return EdgeCaseResult

            def run(self) -> EdgeCaseResult:
                return EdgeCaseResult()

            def _build_components(self) -> None:
                pass

            def _validate_requirements(self) -> None:
                raise ValueError("Validation failed")

        config = EdgeCaseConfig()

        with pytest.raises(ValueError, match="Validation failed"):
            FailingValidatePipeline(config=config)

    def test_pipeline_multiple_instantiations(self) -> None:
        """Test multiple pipeline instances with same config."""
        config = EdgeCaseConfig(test_value="shared")

        pipeline1 = EdgeCasePipeline(config=config)
        pipeline2 = EdgeCasePipeline(config=config)

        assert pipeline1.config == pipeline2.config
        assert pipeline1 is not pipeline2

    def test_pipeline_repr(self) -> None:
        """Test pipeline __repr__ method."""
        config = EdgeCaseConfig()
        pipeline = EdgeCasePipeline(config=config)

        repr_str = repr(pipeline)
        assert "EdgeCasePipeline" in repr_str
        assert "edge_case" in repr_str

    def test_pipeline_without_description(self) -> None:
        """Test pipeline instantiation fails without description ClassVar."""

        with pytest.raises(AttributeError):

            class NoDescriptionPipeline(BasePipeline):
                pipeline_type: ClassVar[str] = "no_desc"
                # description intentionally missing

                @classmethod
                def config_model(cls) -> type[EdgeCaseConfig]:
                    return EdgeCaseConfig

                @classmethod
                def result_model(cls) -> type[EdgeCaseResult]:
                    return EdgeCaseResult

                def run(self) -> EdgeCaseResult:
                    return EdgeCaseResult()

                def _build_components(self) -> None:
                    pass

            config = EdgeCaseConfig()
            NoDescriptionPipeline(config=config)

    def test_pipeline_without_pipeline_type(self) -> None:
        """Test pipeline instantiation fails without pipeline_type ClassVar."""

        with pytest.raises(AttributeError):

            class NoPipelineTypePipeline(BasePipeline):
                # pipeline_type intentionally missing
                description: ClassVar[str] = "No Type"

                @classmethod
                def config_model(cls) -> type[EdgeCaseConfig]:
                    return EdgeCaseConfig

                @classmethod
                def result_model(cls) -> type[EdgeCaseResult]:
                    return EdgeCaseResult

                def run(self) -> EdgeCaseResult:
                    return EdgeCaseResult()

                def _build_components(self) -> None:
                    pass

            config = EdgeCaseConfig()
            NoPipelineTypePipeline(config=config)
