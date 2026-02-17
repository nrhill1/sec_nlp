"""Data models for retrieve pipeline outputs."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines import BasePipelineResult
from sec_nlp.types import JsonValue


class RetrievalHit(BaseModel):
    """Ranked retrieval hit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    query: str
    accession_number: str
    form_type: str
    filed_date: str
    company_name: str
    cik: str
    score: float
    edgar_url: str
    snippet: str | None = None


class RetrieveResult(BasePipelineResult):
    """Result payload for retrieve pipeline."""

    pipeline_type: ClassVar[Literal["retrieve"]] = "retrieve"

    model_config = ConfigDict(frozen=True, extra="ignore")

    symbols_processed: int = Field(
        default=0,
        description="Number of symbols processed by the pipeline.",
    )
    queries_processed: int = Field(
        default=0,
        description="Total symbol-query pairs executed.",
    )
    hits_returned: int = Field(
        default=0,
        description="Total ranked hits written across all symbols.",
    )

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["symbols_processed"] = self.symbols_processed
        fields["queries_processed"] = self.queries_processed
        fields["hits_returned"] = self.hits_returned
        return fields
