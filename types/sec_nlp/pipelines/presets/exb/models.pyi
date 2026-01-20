from typing import ClassVar, Literal

from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.pipelines import BaseResult as BaseResult
from sec_nlp.types import JsonValue as JsonValue

class ExhibitInput(BaseModel):
    model_config: Incomplete
    chunk: str
    symbol: str

class ExhibitContractResult(BaseResult):
    pipeline_type: ClassVar[Literal["exhibit"]]
    model_config: Incomplete
    is_relevant: bool
    relevance_score: float | None
    contract_type: str | None
    contract_category: str | None
    parties: list[str]
    supplier_names: list[str]
    key_terms: list[str]
    obligations: list[str]
    summary: str | None
    has_exclusivity: bool | None
    has_aftermarket_provisions: bool | None
    has_pricing_at_cost: bool | None
    reasoning: str | None
    def summary_fields(self) -> dict[str, JsonValue]: ...

class ExhibitResult(BaseResult):
    pipeline_type: ClassVar[Literal["exhibit"]]
    def summary_fields(self) -> dict[str, JsonValue]: ...
