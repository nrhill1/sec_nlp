# src/sec_nlp/pipelines/presets/chat/models.py
"""Data models for chat pipeline outputs."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.types import JsonValue


class ChatCitation(BaseModel):
    """Citation metadata for an answer source chunk."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    citation_id: str
    collection: str
    score: float
    symbol: str | None = None
    accession_number: str | None = None
    form_type: str | None = None
    filed_date: str | None = None
    source: str | None = None
    snippet: str


class ChatTurn(BaseModel):
    """Single chat turn for transcript export."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["user", "assistant"]
    message: str
    citations: list[str] = Field(default_factory=list)


class ChatTranscriptPayload(BaseModel):
    """Root payload for chat transcript outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_timestamp: str
    run_short_id: int | None = None
    run_id: str
    run_short_id_display: str

    symbol: str
    question: str
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    turns: list[ChatTurn] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ChatResult(BasePipelineResult):
    """Result payload for chat pipeline."""

    pipeline_type: ClassVar[Literal["chat"]] = "chat"

    model_config = ConfigDict(frozen=True, extra="ignore")

    turns_processed: int = Field(
        default=0,
        description="Number of turns present in the exported transcript.",
    )
    hits_retrieved: int = Field(
        default=0,
        description="Number of retrieved vector hits considered for response generation.",
    )
    citations_returned: int = Field(
        default=0,
        description="Number of citations returned for the answer.",
    )
    answer: str | None = Field(
        default=None,
        description="Assistant answer text for the latest question.",
    )
    citation_ids: list[str] = Field(
        default_factory=list,
        description="Citation IDs referenced in the final answer.",
    )

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["turns_processed"] = self.turns_processed
        fields["hits_retrieved"] = self.hits_retrieved
        fields["citations_returned"] = self.citations_returned
        fields["citation_ids"] = self.citation_ids
        return fields
