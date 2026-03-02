# src/sec_nlp/pipelines/tools/market.py
"""LangChain tool wrapper for derived market context analytics."""

from __future__ import annotations

from time import monotonic

from langchain_core.tools import StructuredTool

from sec_nlp.core.market_analytics import (
    MarketContextMetric,
    build_market_context,
)
from sec_nlp.core.types import as_json_dict
from sec_nlp.types import JsonDict

from .schemas import MarketContextToolInput, MarketContextToolOutput


def _check_timeout(
    *,
    started_at: float,
    timeout_seconds: float | None,
    stage: str,
) -> None:
    """Raise timeout error when execution exceeds configured limit."""
    if timeout_seconds is None:
        return
    elapsed = monotonic() - started_at
    if elapsed > timeout_seconds:
        raise TimeoutError(
            f"market_context_tool timed out during {stage} after {elapsed:.2f}s"
        )


def _format_metric_line(
    *,
    metric: MarketContextMetric,
    benchmark: str,
    profile: str,
) -> list[str]:
    """Format one metric line for market context tool output."""
    return_pct = (
        f"{metric.return_pct:+.2f}%" if metric.return_pct is not None else "n/a"
    )
    spread_pct = (
        f"{metric.spread_pct:+.2f}%" if metric.spread_pct is not None else "n/a"
    )
    beta_value = f"{metric.beta:.2f}" if metric.beta is not None else "n/a"

    if profile == "compact":
        return [
            f"- {metric.symbol}: return {return_pct}, spread vs {benchmark} {spread_pct}, beta {beta_value}."
        ]

    max_drawdown = (
        f"{metric.max_drawdown:.2f}%"
        if metric.max_drawdown is not None
        else "n/a"
    )
    atr_value = f"{metric.atr:.4f}" if metric.atr is not None else "n/a"
    std_dev_value = (
        f"{metric.std_dev:.4f}" if metric.std_dev is not None else "n/a"
    )
    volume_spike = (
        f"{metric.volume_spike:.2f}"
        if metric.volume_spike is not None
        else "n/a"
    )
    return [
        f"- {metric.symbol}: return {return_pct} (spread vs {benchmark} {spread_pct}, beta {beta_value}, max drawdown {max_drawdown}).",
        f"- {metric.symbol}: ATR {atr_value}, return std-dev {std_dev_value}, volume spike {volume_spike}, observations {metric.observations}.",
    ]


def _run_market_context_tool(
    *,
    symbols: list[str],
    start_date,
    end_date,
    benchmark: str = "SPY",
    profile: str = "standard",
    timeout_seconds: float | None = 30.0,
) -> JsonDict:
    """Execute market context tool and return structured metrics."""
    started_at = monotonic()
    _check_timeout(
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        stage="setup",
    )
    bundle = build_market_context(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        benchmark=benchmark,
    )
    _check_timeout(
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        stage="market data retrieval",
    )

    lines: list[str] = []
    benchmark_return = next(
        (
            metric.benchmark_return_pct
            for metric in bundle.metrics
            if metric.benchmark_return_pct is not None
        ),
        None,
    )
    if benchmark_return is not None and profile == "standard":
        lines.append(
            f"- Benchmark {bundle.benchmark}: {bundle.window} return {benchmark_return:+.2f}%."
        )

    for metric in bundle.metrics:
        lines.extend(
            _format_metric_line(
                metric=metric,
                benchmark=bundle.benchmark,
                profile=profile,
            )
        )

    output = MarketContextToolOutput(
        window=bundle.window,
        benchmark=bundle.benchmark,
        symbols=bundle.symbols,
        metrics=[
            metric.model_dump(mode="json", exclude_none=True)
            for metric in bundle.metrics
        ],
        lines=lines,
    )
    payload = as_json_dict(output.model_dump(mode="json", exclude_none=True))
    if payload is None:
        raise ValueError("market_context_tool produced a non-JSON payload")
    return payload


market_context_tool = StructuredTool.from_function(
    name="market_context_tool",
    description=(
        "Build deterministic market context metrics (returns, spread, beta, volatility, ATR, drawdown, volume spike) for one or more symbols."
    ),
    func=_run_market_context_tool,
    args_schema=MarketContextToolInput,
)
