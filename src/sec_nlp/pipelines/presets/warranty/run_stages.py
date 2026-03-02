# src/sec_nlp/pipelines/presets/warranty/run_stages.py
"""Runnable stage helpers for warranty pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.runnables import Runnable
from pydantic import Field

from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.pipelines.base.stages import PipelineStageRunnable

if TYPE_CHECKING:
    from .pipeline import WarrantyPipeline


@dataclass(slots=True)
class WarrantyRunState:
    """In-place state carrier for warranty stages from symbol prep to filing output."""

    runtime: WarrantyPipeline
    symbol: str
    start_date: date | None
    end_date: date | None
    html_paths: list[Path] = field(default_factory=list)
    output_files: list[Path] = field(default_factory=list)
    skip_symbol: bool = False


class PrepareSymbolStage(PipelineStageRunnable[WarrantyRunState]):
    """Ingress stage that initializes symbol context and triggers filing downloads."""

    name: str = Field(default="prepare_symbol")

    def _run(self, state: WarrantyRunState) -> WarrantyRunState:
        """Execute this warranty stage and return updated run state."""
        from sec_edgar_downloader import Downloader

        log_divider(logger, color="cyan")
        logger.info("Processing symbol: %s", state.symbol)

        state.runtime._loader.add_symbol(state.symbol)
        downloader = Downloader(
            "SEC NLP Tool",
            state.runtime.config.email,
            str(state.runtime.config.dl_path),
        )
        try:
            filing_count = downloader.get(
                state.runtime.config.mode.form,
                state.symbol,
                after=state.start_date,
                before=state.end_date,
                limit=state.runtime.config.limit,
                download_details=True,
            )
            if filing_count:
                logger.info(
                    "Downloaded %d filings for %s",
                    filing_count,
                    state.symbol,
                )
        except Exception as exc:
            logger.warning("Download failed for %s: %s", state.symbol, exc)
        return state


class ResolveHtmlPathsStage(PipelineStageRunnable[WarrantyRunState]):
    """Resolution stage that discovers local HTML filing paths for symbol processing."""

    name: str = Field(default="resolve_html_paths")

    def _run(self, state: WarrantyRunState) -> WarrantyRunState:
        """Execute this warranty stage and return updated run state."""
        try:
            state.html_paths = state.runtime._loader.html_paths_for_symbol(
                symbol=state.symbol,
                mode=state.runtime.config.mode,
                base=state.runtime.config.dl_path,
                limit=state.runtime.config.limit,
                start_date=state.start_date,
                end_date=state.end_date,
            )
        except FileNotFoundError:
            logger.warning(
                "No filings found for %s in %s",
                state.symbol,
                state.runtime.config.dl_path,
            )
            state.skip_symbol = True
            return state

        if state.html_paths:
            logger.info(
                "Found %d filings for %s",
                len(state.html_paths),
                state.symbol,
            )
            return state

        logger.warning("No filings found for %s", state.symbol)
        state.skip_symbol = True
        return state


class ProcessFilingsStage(PipelineStageRunnable[WarrantyRunState]):
    """Egress processing stage that parses filings and emits symbol output artifacts."""

    name: str = Field(default="process_filings")

    def _run(self, state: WarrantyRunState) -> WarrantyRunState:
        """Execute this warranty stage and return updated run state."""
        if state.skip_symbol:
            return state
        for html_path in state.html_paths:
            state.output_files.extend(
                state.runtime._process_filing(
                    state.symbol,
                    html_path,
                    state.start_date,
                    state.end_date,
                )
            )
        return state


_WARRANTY_STAGES: tuple[PipelineStageRunnable[WarrantyRunState], ...] = (
    PrepareSymbolStage(),
    ResolveHtmlPathsStage(),
    ProcessFilingsStage(),
)


def build_warranty_stage_chain(
    pipeline: WarrantyPipeline,
) -> Runnable[WarrantyRunState, WarrantyRunState]:
    """Build deterministic warranty stage chain."""
    return pipeline.build_configured_stage_chain(stages=_WARRANTY_STAGES)
