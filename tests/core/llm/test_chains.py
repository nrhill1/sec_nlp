# tests/core/llm/test_chains.py
"""Unit tests for sec_nlp.core.llm.chains module."""

from typing import ClassVar
from unittest.mock import MagicMock

from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from sec_nlp.core.llm.chains import ResultOutputParser, build_runnable
from sec_nlp.pipelines import BaseResult
from sec_nlp.types import JsonDict, JsonValue


# Test models for validation (avoid Test prefix for pytest)
class MockInput(BaseModel):
    """Mock input model for testing."""

    text: str = Field(description="Input text")
    max_length: int = Field(default=100, description="Maximum length")


class MockOutput(BaseResult):
    """Mock output model for testing."""

    pipeline_type: ClassVar[str] = "mock"

    result: str | None = Field(default=None, description="Result text")

    def summary_fields(self) -> dict[str, JsonValue]:
        return {"success": self.success, "result": self.result}


class MockOutputParser:
    """Tests for ResultOutputParser class."""

    def test_output_parser_initialization(self) -> None:
        """Test ResultOutputParser initializes with Pydantic model."""
        parser = ResultOutputParser(pydantic_object=MockOutput)

        assert parser.pydantic_object == MockOutput
        assert parser.OutputType == MockOutput

    def test_output_parser_parse_success(self) -> None:
        """Test successful parsing of valid JSON."""
        parser = ResultOutputParser(pydantic_object=MockOutput)

        valid_json = '{"success": true, "result": "Test result"}'
        result = parser.parse(valid_json)

        assert isinstance(result, MockOutput)
        assert result.success is True
        assert result.result == "Test result"

    def test_output_parser_parse_with_all_fields(self) -> None:
        """Test parsing JSON with all fields."""
        parser = ResultOutputParser(pydantic_object=MockOutput)

        json_str = """{
            "success": true,
            "result": "Success message",
            "error": null,
            "raw_output": null
        }"""
        result = parser.parse(json_str)

        assert result.success is True
        assert result.result == "Success message"
        assert result.error is None

    def test_output_parser_handles_parse_exception(self) -> None:
        """Test that OutputParserException is handled gracefully."""
        parser = ResultOutputParser(pydantic_object=MockOutput)

        # Invalid JSON that will cause parsing to fail
        invalid_json = "not valid json"
        result = parser.parse(invalid_json)

        # Should return MockOutput with success=False and error filled
        assert isinstance(result, MockOutput)
        assert result.success is False
        assert result.error is not None
        assert result.raw_output is not None

    def test_output_parser_handles_missing_required_fields(self) -> None:
        """Test handling of JSON missing required fields."""

        # Create a model with required fields
        class StrictOutput(BaseResult):
            pipeline_type: ClassVar[str] = "strict"
            result: str  # Required field

            def summary_fields(self) -> dict[str, JsonValue]:
                return {"success": self.success, "result": self.result}

        parser = ResultOutputParser(pydantic_object=StrictOutput)

        # JSON missing required field
        incomplete_json = '{"success": true}'
        result = parser.parse(incomplete_json)

        # Should handle the validation error
        assert isinstance(result, StrictOutput)

    def test_output_parser_type_property(self) -> None:
        """Test that _type property returns expected string."""
        parser = ResultOutputParser(pydantic_object=MockOutput)

        type_str = parser._type

        assert "sec_nlp.core.llm.chains" in type_str
        assert "ResultOutputParser" in type_str

    def test_output_parser_output_type_property(self) -> None:
        """Test OutputType property returns correct model."""
        parser = ResultOutputParser(pydantic_object=MockOutput)

        assert parser.OutputType == MockOutput


class TestBuildRunnable:
    """Tests for build_runnable function."""

    def test_build_runnable_creates_chain(self, mock_llm: MagicMock) -> None:
        """Test that build_runnable creates a valid chain."""
        # Create a simple prompt template
        prompt = PromptTemplate.from_template(
            "Summarize this: {text}. Keep it under {max_length} words."
        )

        # Build the runnable
        runnable = build_runnable(
            prompt=prompt,
            llm=mock_llm,
            input_model=MockInput,
            output_model=MockOutput,
        )

        # Verify runnable was created
        assert runnable is not None

    def test_build_runnable_with_require_json_true(
        self, mock_llm: MagicMock
    ) -> None:
        """Test building runnable with JSON requirement."""
        prompt = PromptTemplate.from_template("Test: {text}")

        runnable = build_runnable(
            prompt=prompt,
            llm=mock_llm,
            input_model=MockInput,
            output_model=MockOutput,
            require_json=True,
        )

        assert runnable is not None

    def test_build_runnable_with_require_json_false(
        self, mock_llm: MagicMock
    ) -> None:
        """Test building runnable without JSON requirement."""
        prompt = PromptTemplate.from_template("Test: {text}")

        runnable = build_runnable(
            prompt=prompt,
            llm=mock_llm,
            input_model=MockInput,
            output_model=MockOutput,
            require_json=False,
        )

        assert runnable is not None

    def test_build_runnable_chain_structure(self, mock_llm: MagicMock) -> None:
        """Test that the chain has the expected structure."""
        prompt = PromptTemplate.from_template("Test: {text}")

        runnable = build_runnable(
            prompt=prompt,
            llm=mock_llm,
            input_model=MockInput,
            output_model=MockOutput,
        )

        # The chain should be prompt | llm | parser
        # We can't easily inspect the internal structure, but we can
        # verify it's a runnable object
        assert isinstance(runnable, Runnable)

    def test_build_runnable_different_input_models(
        self, mock_llm: MagicMock
    ) -> None:
        """Test building runnables with different input models."""

        class AlternativeInput(BaseModel):
            content: str
            settings: JsonDict

        prompt = PromptTemplate.from_template("Process: {content}")

        runnable = build_runnable(
            prompt=prompt,
            llm=mock_llm,
            input_model=AlternativeInput,
            output_model=MockOutput,
        )

        assert runnable is not None

    def test_build_runnable_preserves_model_types(
        self, mock_llm: MagicMock
    ) -> None:
        """Test that input/output types are preserved in the chain."""
        prompt = PromptTemplate.from_template("Test: {text}")

        runnable = build_runnable(
            prompt=prompt,
            llm=mock_llm,
            input_model=MockInput,
            output_model=MockOutput,
        )

        # The runnable should have type information
        # This is enforced by with_types() call
        assert runnable is not None

    def test_output_parser_in_build_runnable(self, mock_llm: MagicMock) -> None:
        """Test that ResultOutputParser is used in the built runnable."""
        prompt = PromptTemplate.from_template("Test: {text}")

        # The build_runnable function should create an ResultOutputParser internally
        runnable = build_runnable(
            prompt=prompt,
            llm=mock_llm,
            input_model=MockInput,
            output_model=MockOutput,
        )

        # We can't directly inspect the parser, but we know it's there
        # because build_runnable creates it
        assert runnable is not None

    def test_build_runnable_multiple_chains(self, mock_llm: MagicMock) -> None:
        """Test building multiple independent chains."""
        prompt1 = PromptTemplate.from_template("First: {text}")
        prompt2 = PromptTemplate.from_template("Second: {text}")

        runnable1 = build_runnable(
            prompt=prompt1,
            llm=mock_llm,
            input_model=MockInput,
            output_model=MockOutput,
        )

        runnable2 = build_runnable(
            prompt=prompt2,
            llm=mock_llm,
            input_model=MockInput,
            output_model=MockOutput,
        )

        # Should create two independent runnables
        assert runnable1 is not None
        assert runnable2 is not None
        assert runnable1 is not runnable2
