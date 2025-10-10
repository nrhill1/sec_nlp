# sec_nlp/chains/sec_runnable.py
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from pydantic import Field, ValidationError, TypeAdapter
from pydantic.dataclasses import dataclass
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import RunnableLambda

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SummaryPayload:
    """
    Dataclass with Pydantic validation.
    Add .validate_from_json() that uses TypeAdapter under the hood.
    """

    summary: str | None = None
    points: list[str] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    error: str | None = None
    raw_output: str | None = None

    @classmethod
    def _adapter(cls) -> TypeAdapter[SummaryPayload]:
        return TypeAdapter(cls)

    @classmethod
    def validate_from_json(cls, raw: str) -> SummaryPayload:
        """
        Strictly validate a JSON string into SummaryPayload.
        """
        try:
            return cls._adapter().validate_json(raw)
        except ValidationError as e:
            logger.warning(
                "SummaryPayload.validate_from_json: validation failed: %s", e
            )
            return cls(error="Schema validation failed", raw_output=raw)
        except Exception as e:
            # Malformed JSON or unexpected issues
            logger.warning("SummaryPayload.validate_from_json: parse failed: %s", e)
            return cls(error="JSON parse failed", raw_output=raw)


def build_sec_summarizer(
    *,
    prompt: BasePromptTemplate,
    llm: Any,
    require_json: bool = True,
    max_retries: int = 2,
) -> RunnableLambda:
    """
    Build a Runnable that summarizes SEC filing text chunks using the given LLM
    and prompt template.
    """

    def _invoke_with_retry(inputs: dict[str, Any]) -> dict[str, Any]:
        prompt_str = prompt.format_prompt(
            chunk=inputs["chunk"],
            symbol=inputs["symbol"],
            search_term=inputs["search_term"],
        ).to_string()

        last_err: Exception | None = None
        for attempt in range(1, int(max_retries) + 1):
            try:
                raw = llm.invoke(prompt_str)
                if require_json:
                    payload = SummaryPayload.validate_from_json(raw)
                else:
                    payload = SummaryPayload(summary=str(raw))
                return {"summary": asdict(payload)}
            except Exception as e:
                last_err = e
                logger.error(
                    "LLM invoke failed (attempt %d/%d): %s: %s",
                    attempt,
                    max_retries,
                    type(e).__name__,
                    e,
                )

        err_msg = (
            "%s: %s" % (type(last_err).__name__, last_err)
            if last_err
            else "Unknown error"
        )
        return {
            "summary": asdict(
                SummaryPayload(error="LLM invocation failed", raw_output=err_msg)
            )
        }

    return RunnableLambda(_invoke_with_retry)
