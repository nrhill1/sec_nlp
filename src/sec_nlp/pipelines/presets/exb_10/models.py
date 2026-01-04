# src/sec_nlp/pipelines/presets/exb_10/models.py
"""Data models for Exhibit 10 pipeline."""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines import BaseResult
from sec_nlp.types import JsonValue


class Exhibit10Input(BaseModel):
    """Input schema for Exhibit 10 analysis chain."""

    model_config = ConfigDict(frozen=True)

    chunk: str
    symbol: str


class Exhibit10ContractResult(BaseResult):
    """Result container for an Exhibit 10 contract chunk."""

    pipeline_type: ClassVar[Literal["exhibit10"]] = "exhibit10"

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
    )

    is_relevant: bool = Field(
        default=False,
        description="Whether the contract is relevant based on configured categories",
    )
    relevance_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score for relevance (0.0-1.0)",
    )
    contract_type: str | None = Field(
        default=None,
        description="Type of contract (e.g., Supply Agreement, Credit Agreement)",
    )
    contract_category: str | None = Field(
        default=None,
        description="Category: supply, credit, employment, lease, license, service, other",
    )
    parties: list[str] = Field(
        default_factory=list,
        description="All named counterparties",
    )
    supplier_names: list[str] = Field(
        default_factory=list,
        description="List of supplier/vendor names identified",
    )
    key_terms: list[str] = Field(
        default_factory=list,
        description="Key contractual terms found",
    )
    obligations: list[str] = Field(
        default_factory=list,
        description="Key obligations/provisions",
    )
    summary: str | None = Field(
        default=None,
        description="Short summary of the contract and key terms",
    )
    has_exclusivity: bool | None = Field(
        default=False,
        description="Whether contract contains exclusivity provisions",
    )
    has_aftermarket_provisions: bool | None = Field(
        default=False,
        description="Whether contract mentions aftermarket/repair/maintenance",
    )
    has_pricing_at_cost: bool | None = Field(
        default=False,
        description="Whether contract mentions at-cost or near-cost pricing",
    )
    reasoning: str | None = Field(
        default=None,
        description="Explanation of the analysis",
    )

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["relevance"] = self.relevance_score
        return fields


class Exhibit10Result(BaseResult):
    """Result model for overall Exhibit 10 pipeline."""

    pipeline_type: ClassVar[Literal["exhibit10"]] = "exhibit10"

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        return fields
