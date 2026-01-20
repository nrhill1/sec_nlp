from typing import override

from langchain_core.language_models import (
    BaseLanguageModel as BaseLanguageModel,
)
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts.base import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import (
    Runnable as Runnable,
    RunnableSerializable as RunnableSerializable,
)
from pydantic import BaseModel as BaseModel

from sec_nlp.pipelines import BasePipelineResult as BasePipelineResult

class ResultOutputParser[R: BasePipelineResult](PydanticOutputParser[R]):
    pydantic_object: type[R]
    def __init__(self, pydantic_object: type[R]) -> None: ...
    def parse(self, text: str) -> R: ...
    @property
    @override
    def OutputType(self) -> type[R]: ...

type InputModelKeys = (
    str | int | float | bool | None | list[str] | dict[str, str]
)

def build_runnable[I: BaseModel, R: BasePipelineResult](
    *,
    prompt: BasePromptTemplate,
    llm: BaseLanguageModel[str],
    input_model: type[I],
    output_model: type[R],
    require_json: bool = True,
) -> Runnable[I, R]: ...
