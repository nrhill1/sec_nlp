# sec_nlp/chains/sec_runnable.py
from __future__ import annotations

from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable, RunnableSerializable
from pydantic import BaseModel, Field

from sec_nlp.core.config import get_logger

logger = get_logger(__name__)


__all__: list[str] = ["SummarizationInput", "SummarizationOutput", "build_summarization_runnable"]


class SummarizationInput(BaseModel):
    """Input schema for the SEC summarization chain."""

    chunk: str
    symbol: str
    search_term: str


class SummarizationOutput(BaseModel):
    """Pydantic dataclass representing a validated LLM summary payload."""

    summary: str | None = Field(default=None)
    points: list[str] | None = Field(default=None)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    error: str | None = Field(default=None)
    raw_output: str | None = Field(default=None)


class SummarizationParser(PydanticOutputParser[SummarizationOutput]):
    def parse(self, text: str) -> SummarizationOutput:
        try:
            output: SummarizationOutput = super().parse(text)
            return output
        except OutputParserException as e:
            return SummarizationOutput(error=e.observation, raw_output=e.llm_output)


def build_summarization_runnable(
    *,
    prompt: BasePromptTemplate[Any],
    llm: BaseLanguageModel[Any],
    require_json: bool = True,
) -> Runnable[SummarizationInput, SummarizationOutput]:
    """
    Build the SEC summarization chain:
      input:  SummarizationInput
      pipe:   prompt -> llm -> validation
      output: SummarizationOutput
    """

    chain: RunnableSerializable[Any, SummarizationOutput] = prompt | llm | SummarizationOutput()

    return chain.with_types(input_type=SummarizationInput, output_type=SummarizationOutput)
