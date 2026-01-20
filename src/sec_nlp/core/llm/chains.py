# src/sec_nlp/core/llm/chains.py

from typing import override

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable, RunnableSerializable
from pydantic import BaseModel

from sec_nlp.pipelines import BasePipelineResult


class ResultOutputParser[R: BasePipelineResult](
    PydanticOutputParser[R],
):
    """Output parser to validate and format LLM output."""

    pydantic_object: type[R]

    def __init__(self, pydantic_object: type[R]) -> None:
        """Initialize with the actual Pydantic model class."""
        super().__init__(pydantic_object=pydantic_object)

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
        return f"sec_nlp.core.llm.chains.ResultOutputParser[{self.pydantic_object.__name__}]"

    @property
    @override
    def OutputType(self) -> type[R]:
        """Return the Pydantic model."""
        return self.pydantic_object


type InputModelKeys = (
    str | int | float | bool | None | list[str] | dict[str, str]
)


def build_runnable[
    I: BaseModel,
    R: BasePipelineResult,
](
    *,
    prompt: BasePromptTemplate,
    llm: BaseLanguageModel[str],
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
    parser = ResultOutputParser(pydantic_object=output_model)

    # Convert Pydantic input to dict for prompt template
    def model_to_dict(
        input: I,
    ) -> dict[
        str,
        InputModelKeys | list[InputModelKeys] | dict[str, InputModelKeys],
    ]:
        return input.model_dump()

    chain: RunnableSerializable[I, R] = model_to_dict | prompt | llm | parser
    return chain
