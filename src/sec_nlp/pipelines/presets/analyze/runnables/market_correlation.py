"""Market correlation runnable for the analyze pipeline."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.types import AnalysisResultDict
from sec_nlp.types import JsonDict, JsonValue

from ..io.formats.market_correlation import build_market_correlation
from ..market import MarketEnrichment


class MarketCorrelationInput(BaseModel):
    """Runnable input for market correlation."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    market_data: MarketEnrichment | None = None
    relevant_results: list[AnalysisResultDict] = Field(default_factory=list)


class MarketCorrelationRunnable(
    RunnableSerializable[MarketCorrelationInput, JsonDict | None]
):
    """Compute market correlation metrics for analysis results."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    def invoke(
        self,
        input: MarketCorrelationInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> JsonDict | None:
        _ = config
        _ = kwargs
        return build_market_correlation(
            input.market_data,
            input.relevant_results,
        )
