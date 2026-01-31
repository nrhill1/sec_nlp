"""EFTS search runnable for the analyze pipeline."""

from __future__ import annotations

from datetime import date

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.types import JsonValue

from ..config import EFTSConfig
from ..steps.search.efts_search import EFTSSearchResult, run_efts_search


class EFTSSearchInput(BaseModel):
    """Runnable input for EFTS searches."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    symbol: str
    queries: list[str]
    local_accessions: set[str] = Field(default_factory=set)


class EFTSSearchRunnable(
    RunnableSerializable[EFTSSearchInput, list[EFTSSearchResult]]
):
    """Run EFTS searches for a symbol/query set."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    efts_config: EFTSConfig = Field(description="EFTS configuration")
    forms: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    email: str = Field(description="Contact email for SEC API requests")

    def invoke(
        self,
        input: EFTSSearchInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> list[EFTSSearchResult]:
        _ = config
        _ = kwargs
        symbol = input.symbol
        if not symbol or not input.queries:
            return []
        return run_efts_search(
            efts_config=self.efts_config,
            symbols=[symbol],
            forms=self.forms,
            start_date=self.start_date,
            end_date=self.end_date,
            queries=input.queries,
            email=self.email,
            local_accessions=input.local_accessions,
        )
