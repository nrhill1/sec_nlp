# sec_nlp/chains/sec_runnable.py
from __future__ import annotations

import json
from typing import Any, ClassVar, Literal, TypedDict

from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda, RunnableSerializable
from pydantic import Field, TypeAdapter, ValidationError
from pydantic.dataclasses import dataclass

from sec_nlp.core.config import get_logger

logger = get_logger(__name__)


__all__: list[str] = ["SummarizationInput", "SummarizationOutput", "build_summarization_runnable"]


class SummarizationInput(TypedDict):
    """Input schema for the SEC summarization chain."""

    chunk: str
    symbol: str
    search_term: str


class SummarizationResult(TypedDict, total=False):
    """Validated summary structure returned by the LLM."""

    summary: str | None
    points: list[str] | None
    confidence: float | None
    error: str | None
    raw_output: str | None


class SummarizationOutput(TypedDict):
    """Final runnable output, wrapping the summary and status."""

    status: Literal["ok", "error"]
    summary: SummarizationResult


@dataclass(slots=True)
class SummaryPayload:
    """Pydantic dataclass representing a validated LLM summary payload."""

    summary: str | None = Field(default=None)
    points: list[str] | None = Field(default=None)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    error: str | None = Field(default=None)
    raw_output: str | None = Field(default=None)

    _ADAPTER: ClassVar[TypeAdapter[SummaryPayload] | None] = None

    @classmethod
    def _adapter(cls) -> TypeAdapter[SummaryPayload]:
        if cls._ADAPTER is None:
            cls._ADAPTER = TypeAdapter(cls)
        return cls._ADAPTER

    @classmethod
    def validate_from_json(cls, raw: str) -> SummaryPayload:
        """Strictly parse JSON string → dict → validate into a frozen instance."""
        try:
            data = json.loads(raw)
        except Exception as e:
            logger.warning("SummaryPayload: JSON parse failed: %s", e)
            return cls(error="JSON parse failed", raw_output=raw)

        if isinstance(data, dict):
            s = data.get("summary")
            if isinstance(s, str):
                s = s.strip()
                data["summary"] = s or None
            pts = data.get("points")
            if isinstance(pts, list):
                data["points"] = [p.strip() for p in pts if isinstance(p, str) and p.strip()]

        try:
            return cls._adapter().validate_python(data)
        except ValidationError as e:
            logger.warning("SummaryPayload: schema validation failed: %s", e)
            return cls(error="Schema validation failed", raw_output=raw)


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

    def _validate(raw: str) -> SummarizationOutput:
        if require_json:
            payload = SummaryPayload.validate_from_json(raw)
        else:
            payload = SummaryPayload(summary=raw)

        status: Literal["ok", "error"] = "ok" if payload.error is None else "error"
        result_dict = SummaryPayload._adapter().dump_python(payload)
        result: SummarizationResult = result_dict
        return {"status": status, "summary": result}

    validate: Runnable[str, SummarizationOutput] = RunnableLambda(_validate)

    chain: RunnableSerializable[Any, SummarizationOutput] = prompt | llm | validate

    return chain.with_types(input_type=SummarizationInput, output_type=SummarizationOutput)
