"""Sector-level correlation runnable for the analyze pipeline."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig, RunnableSerializable
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.market import MarketRetriever
from sec_nlp.core.stats.sector import sector_correlation
from sec_nlp.types import JsonValue


class SectorCorrelationInput(BaseModel):
    """Runnable input for sector correlation calculations."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    symbols: list[str] = Field(default_factory=list)
    days: int = Field(default=252, ge=2)
    metric: str = Field(default="price_return")


class SectorCorrelationOutput(BaseModel):
    """Correlation matrix output for a symbol set."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    symbols: list[str] = Field(default_factory=list)
    correlation_matrix: dict[str, dict[str, float | None]] = Field(
        default_factory=dict
    )
    strongest_pair: tuple[str, str] | None = None
    strongest_correlation: float | None = None


class SectorCorrelationRunnable(
    RunnableSerializable[SectorCorrelationInput, SectorCorrelationOutput]
):
    """Compute pairwise return correlation and identify the strongest pair."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    retriever: MarketRetriever | None = None

    def invoke(
        self,
        input: SectorCorrelationInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> SectorCorrelationOutput:
        _ = config
        _ = kwargs
        symbols = self._normalize_symbols(input.symbols)
        if not symbols:
            return SectorCorrelationOutput()

        sector_results = sector_correlation(
            symbols,
            metric=input.metric,
            days=input.days,
            symbol_to_sic=dict.fromkeys(symbols, "SECTOR"),
            retriever=self.retriever,
        )
        if not sector_results:
            return SectorCorrelationOutput(symbols=symbols)

        matrix = sector_results[0].correlation_matrix
        output_symbols = sector_results[0].symbols
        strongest_pair, strongest_correlation = self._strongest_pair(
            output_symbols,
            matrix,
        )
        return SectorCorrelationOutput(
            symbols=output_symbols,
            correlation_matrix=matrix,
            strongest_pair=strongest_pair,
            strongest_correlation=strongest_correlation,
        )

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        return sorted(
            {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        )

    @staticmethod
    def _strongest_pair(
        symbols: list[str],
        matrix: dict[str, dict[str, float | None]],
    ) -> tuple[tuple[str, str] | None, float | None]:
        best_pair: tuple[str, str] | None = None
        best_value: float | None = None
        best_abs = -1.0

        for index, left in enumerate(symbols):
            row = matrix.get(left, {})
            for right in symbols[index + 1 :]:
                value = row.get(right)
                if value is None:
                    continue
                abs_value = abs(value)
                if abs_value > best_abs:
                    best_abs = abs_value
                    best_pair = (left, right)
                    best_value = value

        return best_pair, best_value
