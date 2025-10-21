from typing import Literal, Self, TypedDict

from langchain_core.prompt_values import PromptValue
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable

__all__ = ["SummarizationInput", "SummarizationOutput", "build_summarization_runnable"]

class SummarizationInput(TypedDict):
    chunk: str
    symbol: str
    search_term: str

class SummarizationResult(TypedDict, total=False):
    summary: str | None
    points: list[str] | None
    confidence: float | None
    error: str | None
    raw_output: str | None

class SummarizationOutput(TypedDict):
    status: Literal["ok", "error"]
    summary: SummarizationResult

class SummaryPayload:
    summary: str | None
    points: list[str] | None
    confidence: float | None
    error: str | None
    raw_output: str | None
    @classmethod
    def validate_from_json(cls, raw: str) -> Self: ...

def build_summarization_runnable(
    *, prompt: BasePromptTemplate, llm: Runnable[str | PromptValue, str], require_json: bool = True
) -> Runnable[SummarizationInput, SummarizationOutput]: ...
