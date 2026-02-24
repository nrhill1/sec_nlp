# tests/pipelines/presets/test_phase_progress_timers.py
"""Progress phase timer behavior across preset pipelines."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from sec_nlp.pipelines.presets.analyze.pipeline import AnalyzePipeline
from sec_nlp.pipelines.presets.events.pipeline import EventsPipeline
from sec_nlp.pipelines.presets.financials.pipeline import FinancialsPipeline
from sec_nlp.pipelines.presets.holdings.pipeline import HoldingsPipeline
from sec_nlp.pipelines.presets.insider.pipeline import InsiderPipeline
from sec_nlp.pipelines.presets.news.pipeline import NewsPipeline
from sec_nlp.pipelines.presets.retrieve.pipeline import RetrievePipeline


@pytest.mark.parametrize(
    "pipeline_cls",
    [
        AnalyzePipeline,
        NewsPipeline,
        HoldingsPipeline,
        FinancialsPipeline,
        InsiderPipeline,
    ],
)
def test_update_phase_resets_timer_for_indeterminate_step(
    pipeline_cls: type,
) -> None:
    pipeline = object.__new__(pipeline_cls)
    if pipeline_cls is AnalyzePipeline:
        pipeline._phase_start = 0.0  # pyright: ignore[reportAttributeAccessIssue]

    progress = Mock()
    pipeline._update_phase(  # pyright: ignore[reportAttributeAccessIssue]
        progress,
        7,
        "AAPL",
        "Loading",
        total=None,
    )

    progress.reset.assert_called_once()
    progress.update.assert_called_once_with(7, total=None, completed=0)


@pytest.mark.parametrize(
    "pipeline_cls",
    [
        AnalyzePipeline,
        NewsPipeline,
        HoldingsPipeline,
        FinancialsPipeline,
        InsiderPipeline,
    ],
)
def test_update_phase_resets_timer_for_determinate_step(
    pipeline_cls: type,
) -> None:
    pipeline = object.__new__(pipeline_cls)
    if pipeline_cls is AnalyzePipeline:
        pipeline._phase_start = 0.0  # pyright: ignore[reportAttributeAccessIssue]

    progress = Mock()
    pipeline._update_phase(  # pyright: ignore[reportAttributeAccessIssue]
        progress,
        9,
        "AAPL",
        "Parsing",
        total=3,
    )

    progress.reset.assert_called_once()
    reset_kwargs = progress.reset.call_args.kwargs
    assert reset_kwargs.get("total") == 3
    progress.update.assert_not_called()


@pytest.mark.parametrize("pipeline_cls", [EventsPipeline, RetrievePipeline])
def test_update_phase_resets_timer_for_simple_step(
    pipeline_cls: type,
) -> None:
    pipeline = object.__new__(pipeline_cls)
    progress = Mock()

    pipeline._update_phase(  # pyright: ignore[reportAttributeAccessIssue]
        progress,
        11,
        "AAPL",
        "Scanning",
    )

    progress.reset.assert_called_once()
    progress.update.assert_called_once_with(11, total=None, completed=0)
