"""EFTS search runnable for the analyze pipeline."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from ..config import AnalyzeConfig
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

    config: AnalyzeConfig = Field(description="Analyze pipeline config")
    email: str = Field(description="Contact email for SEC API requests")

    def invoke(
        self,
        input: EFTSSearchInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> list[EFTSSearchResult]:
        _ = config
        _ = kwargs
        symbol = input.symbol
        if not symbol or not input.queries:
            return []
        run_config = self.config.model_copy(update={"symbols": [symbol]})
        return run_efts_search(
            config=run_config,
            queries=input.queries,
            email=self.email,
            local_accessions=input.local_accessions,
        )
