from langchain_core.prompt_values import PromptValue
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable
from pydantic import TypeAdapter
from typing import ClassVar, Literal, TypedDict

__all__ = ['SummarizationInput', 'SummarizationOutput', 'build_summarization_runnable']

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
    status: Literal['ok', 'error']
    summary: SummarizationResult

class SummaryPayload:
    summary: str | None
    points: list[str] | None
    confidence: float | None
    error: str | None
    raw_output: str | None
    _ADAPTER: ClassVar[TypeAdapter[SummaryPayload] | None]
    @classmethod
    def _adapter(cls) -> TypeAdapter[SummaryPayload]: ...
    @classmethod
    def validate_from_json(cls, raw: str) -> SummaryPayload: ...

def build_summarization_runnable(*, prompt: BasePromptTemplate, llm: Runnable[str | PromptValue, str], require_json: bool = True) -> Runnable[SummarizationInput, SummarizationOutput]: ...
