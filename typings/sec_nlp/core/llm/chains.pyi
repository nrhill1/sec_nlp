from typing import Any

from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel
from typing_extensions import override

__all__ = ["SummarizationInput", "SummarizationOutput", "build_summarization_runnable"]

class SummarizationInput(BaseModel):
    chunk: str
    symbol: str
    search_term: str

class SummarizationOutput(BaseModel):
    summary: str | None
    points: list[str] | None
    confidence: float | None
    error: str | None
    raw_output: str | None

class SummarizationOutputParser(PydanticOutputParser[SummarizationOutput]):
    pydantic_object: type[SummarizationOutput]
    def parse(self, text: str) -> SummarizationOutput: ...
    @property
    def _type(self) -> str: ...
    @property
    @override
    def OutputType(self) -> type[SummarizationOutput]: ...

def build_summarization_runnable(
    *, prompt: BasePromptTemplate[Any], llm: BaseLanguageModel[Any], require_json: bool = True
) -> Runnable[SummarizationInput, SummarizationOutput]: ...
