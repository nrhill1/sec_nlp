from typing import ClassVar, Literal

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.pipelines import BasePipelineResult as BasePipelineResult
from sec_nlp.types import JsonValue as JsonValue

class WarrantyResult(BasePipelineResult):
    model_config: Incomplete
    pipeline_type: ClassVar[Literal["warranty"]]
    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None
    period: str | None
    confidence: float | None
    def summary_fields(self) -> dict[str, JsonValue]: ...

class WarrantyInput(BaseModel):
    model_config: Incomplete
    chunk: str
    symbol: str
