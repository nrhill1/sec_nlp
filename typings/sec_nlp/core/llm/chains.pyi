from typing import Annotated, Any

from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable
from langchain_core.utils import TBaseModel
from pydantic import BaseModel

__all__ = ['SummarizationInput', 'SummarizationOutput', 'build_summarization_runnable']

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

class SummarizationParser(PydanticOutputParser):
    pydantic_object: Annotated[type[TBaseModel], None]
    def parse(self, text: str): ...

def build_summarization_runnable(*, prompt: BasePromptTemplate[Any], llm: BaseLanguageModel[Any], require_json: bool = True) -> Runnable[SummarizationInput, SummarizationOutput]: ...
