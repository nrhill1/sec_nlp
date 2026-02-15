from typing import ClassVar, Literal

from pydantic import BaseModel

from sec_nlp.pipelines import BasePipelineResult as BasePipelineResult
from sec_nlp.types import JsonValue as JsonValue

class InsiderTransaction(BaseModel):
    symbol: str
    accession_number: str
    form_type: str
    filed_date: str | None
    transaction_id: str | None
    transaction_index: int | None
    transaction_date: str | None
    owner_name: str | None
    owner_cik: int | None
    relationship_roles: list[str]
    officer_title: str | None
    security_title: str | None
    transaction_code: str | None
    transaction_type: str | None
    ownership_type: str | None
    transaction_shares: float | None
    transaction_price: float | None
    shares_owned_following_transaction: float | None
    direct_or_indirect: str | None
    source_file: str | None
    @property
    def transaction_value(self) -> float | None: ...

class InsiderLedger(BaseModel):
    owner_key: str
    owner_name: str | None
    owner_cik: int | None
    total_transactions: int
    buy_transactions: int
    sell_transactions: int
    net_shares: float
    net_value: float
    first_transaction_date: str | None
    last_transaction_date: str | None

class InsiderAlert(BaseModel):
    symbol: str
    alert_type: str
    severity: Literal["low", "medium", "high"]
    message: str
    transaction_date: str | None
    accession_number: str | None
    owner_names: list[str]
    related_transaction_ids: list[str]

class InsiderResult(BasePipelineResult):
    pipeline_type: ClassVar[Literal["insider"]]
    symbols_processed: int
    transactions_processed: int
    alerts_generated: int
    def summary_fields(self) -> dict[str, JsonValue]: ...
