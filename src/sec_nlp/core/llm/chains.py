# src/sec_nlp/core/llm/chains.py
from __future__ import annotations

from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable, RunnableSerializable
from typing_extensions import override

from sec_nlp.core.logging import get_logger
from sec_nlp.pipelines.base import I, R

logger = get_logger(__name__)


class OutputParser(PydanticOutputParser[R]):
    """Output parser to validate and format LLM output."""

    pydantic_object: type[R]

    def __init__(self, pydantic_object: type[R], **kwargs: Any) -> None:
        """Initialize with the actual Pydantic model class."""
        super().__init__(pydantic_object=pydantic_object, **kwargs)

    def parse(self, text: str) -> R:
        try:
            output: R = super().parse(text)
            return output
        except OutputParserException as e:
            return self.pydantic_object(
                success=False, error=e.observation, raw_output=e.llm_output
            )

    @property
    def _type(self) -> str:
        return f"sec_nlp.core.llm.chains.{str(self.pydantic_object)[1:]}OutputParser"

    @property
    @override
    def OutputType(self) -> type[R]:
        """Return the Pydantic model."""
        return self.pydantic_object


def build_runnable(
    *,
    prompt: BasePromptTemplate[Any],
    llm: BaseLanguageModel[Any],
    input_model: type[I],
    output_model: type[R],
    require_json: bool = True,
) -> Runnable[I, R]:
    """
    Build the SEC summarization chain:
      input:  I (e.g., SummarizationInput)
      pipe:   prompt -> llm -> validation
      output: R (e.g., SummarizationOutput)

    Args:
        prompt: The prompt template
        llm: The language model
        output_model: The Pydantic model class for output validation
        input_model: The Pydantic model class for input validation
        require_json: Whether to require JSON output

    Returns:
        Runnable[I, R]: A runnable chain with input and output models specific to that pipeline.
    """
    parser = OutputParser(pydantic_object=output_model)
    chain: RunnableSerializable[Any, R] = prompt | llm | parser
    return chain.with_types(input_type=input_model, output_type=output_model)
