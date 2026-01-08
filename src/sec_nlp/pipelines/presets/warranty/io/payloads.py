# src/sec_nlp/pipelines/presets/warranty/io/payloads.py
"""Payload models for warranty exports."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.types import JsonValue


class WarrantyPeriodPayload(BaseModel):
    """Optional fields for warranty period records."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    symbol: JsonValue | None = None
    period: JsonValue | None = None
    period_end: JsonValue | None = None
    warranty_liability: float | None = None
    warranty_payout: float | None = None
    net_revenue: float | None = None
    confidence: float | None = None
    source: JsonValue | None = None
    accession_number: JsonValue | None = None
    xbrl_conflicted_fields: list[JsonValue] | None = None
    warranty_liability_sources: JsonValue | None = None
    warranty_payout_sources: JsonValue | None = None
    net_revenue_sources: JsonValue | None = None


class WarrantySummaryPayload(BaseModel):
    """Summary stats for warranty exports."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    periods_found: int
    xbrl_periods: int
    llm_periods: int
    latest_period: JsonValue | None = None
    latest_liability: float | None = None


class WarrantyProcessingPayload(BaseModel):
    """Processing metadata for warranty exports."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    chunks_analyzed: int
    xbrl_facts_found: int
    llm_extractions: int
    llm_with_data: int
    errors: int


class WarrantyOutputPayload(BaseModel):
    """Root payload for warranty exports."""

    model_config = ConfigDict(frozen=True, extra="forbid", defer_build=True)

    symbol: JsonValue
    form_type: JsonValue
    periods: list[WarrantyPeriodPayload] = Field(default_factory=list)
    summary: WarrantySummaryPayload
    processing: WarrantyProcessingPayload
