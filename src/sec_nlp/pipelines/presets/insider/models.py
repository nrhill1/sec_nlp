"""Data models for insider pipeline."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines import BasePipelineResult
from sec_nlp.types import JsonValue


class InsiderTransaction(BaseModel):
    """Normalized insider transaction extracted from Form 3/4/5 filings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    accession_number: str
    form_type: str
    filed_date: str | None = None
    transaction_id: str | None = None
    transaction_index: int | None = None
    transaction_date: str | None = None
    owner_name: str | None = None
    owner_cik: int | None = None
    relationship_roles: list[str] = Field(default_factory=list)
    officer_title: str | None = None
    security_title: str | None = None
    transaction_code: str | None = None
    transaction_type: str | None = None
    ownership_type: str | None = None
    transaction_shares: float | None = None
    transaction_price: float | None = None
    shares_owned_following_transaction: float | None = None
    direct_or_indirect: str | None = None
    source_file: str | None = None

    @property
    def transaction_value(self) -> float | None:
        if self.transaction_shares is None or self.transaction_price is None:
            return None
        return self.transaction_shares * self.transaction_price


class InsiderLedger(BaseModel):
    """Per-insider aggregate ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_key: str
    owner_name: str | None = None
    owner_cik: int | None = None
    total_transactions: int = 0
    buy_transactions: int = 0
    sell_transactions: int = 0
    net_shares: float = 0.0
    net_value: float = 0.0
    first_transaction_date: str | None = None
    last_transaction_date: str | None = None


class InsiderAlert(BaseModel):
    """Alert generated from insider trade heuristics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    alert_type: str
    severity: Literal["low", "medium", "high"]
    message: str
    transaction_date: str | None = None
    accession_number: str | None = None
    owner_names: list[str] = Field(default_factory=list)
    related_transaction_ids: list[str] = Field(default_factory=list)


class InsiderResult(BasePipelineResult):
    """Result payload for insider pipeline."""

    pipeline_type: ClassVar[Literal["insider"]] = "insider"

    model_config = ConfigDict(frozen=True, extra="ignore")

    symbols_processed: int = Field(
        default=0,
        description="Number of symbols processed by the pipeline.",
    )
    transactions_processed: int = 0
    alerts_generated: int = 0

    def summary_fields(self) -> dict[str, JsonValue]:
        fields: dict[str, JsonValue] = {}
        fields.update(self.base_summary_fields())
        fields["symbols_processed"] = self.symbols_processed
        fields["transactions_processed"] = self.transactions_processed
        fields["alerts_generated"] = self.alerts_generated
        return fields
