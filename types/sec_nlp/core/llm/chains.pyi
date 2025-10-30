from typing import Any

from _typeshed import Incomplete
from langchain_core.language_models import (
    BaseLanguageModel as BaseLanguageModel,
)
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts.base import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from langchain_core.runnables import (
    RunnableSerializable as RunnableSerializable,
)
from typing_extensions import override

from sec_nlp.core.logging import get_logger as get_logger
from sec_nlp.pipelines.base import I as I
from sec_nlp.pipelines.base import R as R

logger: Incomplete

class OutputParser(PydanticOutputParser[R]):
    pydantic_object: type[R]
    def __init__(self, pydantic_object: type[R], **kwargs: Any) -> None: ...
    def parse(self, text: str) -> R: ...
    @property
    def _type(self) -> str: ...
    @property
    @override
    def OutputType(self) -> type[R]: ...

def build_runnable(
    *,
    prompt: BasePromptTemplate[Any],
    llm: BaseLanguageModel[Any],
    input_model: type[I],
    output_model: type[R],
    require_json: bool = True,
) -> Runnable[I, R]: ...
