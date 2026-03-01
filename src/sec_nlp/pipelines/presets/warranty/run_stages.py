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
    """Mutable in-process state shared across warranty runnable stages."""

    symbol: str
    start_date: date | None
    end_date: date | None
    html_paths: list[Path] = field(default_factory=list)
    output_files: list[Path] = field(default_factory=list)
    skip_symbol: bool = False


def create_initial_warranty_state(
    *,
    symbol: str,
    start_date: date | None,
    end_date: date | None,
) -> WarrantyRunState:
    """Create initial mutable state for warranty stage execution."""
    return WarrantyRunState(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )


class PrepareSymbolStage(PipelineStageRunnable[WarrantyRunState]):
    """Initialize symbol context and trigger filing downloads."""

    pipeline: WarrantyPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="prepare_symbol")

    def _run(self, state: WarrantyRunState) -> WarrantyRunState:
        """Execute this warranty stage and return updated run state."""
        from sec_edgar_downloader import Downloader

        log_divider(logger, color="cyan")
        logger.info("Processing symbol: %s", state.symbol)

        self.pipeline._loader.add_symbol(state.symbol)
        downloader = Downloader(
            "SEC NLP Tool",
            self.pipeline.config.email,
            str(self.pipeline.config.dl_path),
        )
        try:
            filing_count = downloader.get(
                self.pipeline.config.mode.form,
                state.symbol,
                after=state.start_date,
                before=state.end_date,
                limit=self.pipeline.config.limit,
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
    """Resolve filing HTML paths for one symbol."""

    pipeline: WarrantyPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="resolve_html_paths")

    def _run(self, state: WarrantyRunState) -> WarrantyRunState:
        """Execute this warranty stage and return updated run state."""
        try:
            state.html_paths = self.pipeline._loader.html_paths_for_symbol(
                symbol=state.symbol,
                mode=self.pipeline.config.mode,
                base=self.pipeline.config.dl_path,
                limit=self.pipeline.config.limit,
                start_date=state.start_date,
                end_date=state.end_date,
            )
        except FileNotFoundError:
            logger.warning(
                "No filings found for %s in %s",
                state.symbol,
                self.pipeline.config.dl_path,
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
    """Process each filing path and emit symbol output files."""

    pipeline: WarrantyPipeline = Field(exclude=True, repr=False)
    name: str = Field(default="process_filings")

    def _run(self, state: WarrantyRunState) -> WarrantyRunState:
        """Execute this warranty stage and return updated run state."""
        if state.skip_symbol:
            return state
        for html_path in state.html_paths:
            state.output_files.extend(
                self.pipeline._process_filing(
                    state.symbol,
                    html_path,
                    state.start_date,
                    state.end_date,
                )
            )
        return state


def build_warranty_stage_chain(
    pipeline: WarrantyPipeline,
) -> Runnable[WarrantyRunState, WarrantyRunState]:
    """Build deterministic warranty stage chain."""
    types_namespace = {"WarrantyPipeline": pipeline.__class__}
    PrepareSymbolStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    ResolveHtmlPathsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    ProcessFilingsStage.model_rebuild(
        _types_namespace=types_namespace,
        force=True,
    )
    stages: tuple[PipelineStageRunnable[WarrantyRunState], ...] = (
        PrepareSymbolStage(pipeline=pipeline),
        ResolveHtmlPathsStage(pipeline=pipeline),
        ProcessFilingsStage(pipeline=pipeline),
    )
    configured_stages = tuple(
        stage.configured(
            pipeline_type=pipeline.pipeline_type,
            run_id=str(pipeline.config.run_id),
        )
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
