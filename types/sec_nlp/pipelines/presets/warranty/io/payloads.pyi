from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.types import JsonValue as JsonValue

class WarrantyPeriodPayload(BaseModel):
    model_config: Incomplete
    symbol: JsonValue | None
    period: JsonValue | None
    period_end: JsonValue | None
    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None
    confidence: float | None
    source: JsonValue | None
    accession_number: JsonValue | None
    xbrl_conflicted_fields: list[JsonValue] | None
    warranty_liability_sources: JsonValue | None
    warranty_payout_sources: JsonValue | None
    net_revenue_sources: JsonValue | None

class WarrantySummaryPayload(BaseModel):
    model_config: Incomplete
    periods_found: int
    xbrl_periods: int
    llm_periods: int
    latest_period: JsonValue | None
    latest_liability: float | None

class WarrantyProcessingPayload(BaseModel):
    model_config: Incomplete
    chunks_analyzed: int
    xbrl_facts_found: int
    llm_extractions: int
    llm_with_data: int
    errors: int

class WarrantyOutputPayload(BaseModel):
    model_config: Incomplete
    symbol: JsonValue
    form_type: JsonValue
    periods: list[WarrantyPeriodPayload]
    summary: WarrantySummaryPayload
    processing: WarrantyProcessingPayload
