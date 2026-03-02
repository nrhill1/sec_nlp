# src/sec_nlp/pipelines/presets/news/pipeline.py
"""Pipeline for monitoring company-centric financial news."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

from langchain_core.runnables import Runnable
from pydantic import PrivateAttr
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.core.types import coerce_result_json_dict
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import build_run_output_context
from sec_nlp.types import ResultDict

from .config import NewsSettings
from .io import (
    NewsTimelinePayload,
    write_news_timeline_csv,
    write_news_timeline_json,
    write_news_timeline_yaml,
)
from .models import NewsCorrelation, NewsHeadline, NewsResult, NewsTimelineEntry
from .run_stages import (
    NewsRunState,
    build_news_stage_chain,
    create_initial_news_state,
)


class NewsPipeline(BasePipeline):
    """Fetch, score, correlate, and export financial news timelines."""

    pipeline_type: ClassVar[Literal["news"]] = "news"
    description: ClassVar[str] = (
        "Monitor financial news, score topic relevance, and correlate with filings and market moves"
    )
    requires_llm: ClassVar[bool] = False

    config: NewsSettings
    _stage_chain: Runnable[NewsRunState, NewsRunState] | None = PrivateAttr(
        default=None
    )

    @classmethod
    def config_model(cls) -> type[NewsSettings]:
        return NewsSettings

    @classmethod
    def result_model(cls) -> type[NewsResult]:
        return NewsResult

    def _build_components(self) -> None:
        """Initialize reusable components for news pipeline execution."""
        self._stage_chain = build_news_stage_chain(self)

    def run(self) -> NewsResult:
        try:
            self.config.setup_paths()
            outputs: list[Path] = []
            metadata: ResultDict = {}
            items_fetched = 0
            items_emitted = 0
            clusters_detected = 0

            console = get_rich_console()
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(complete_style="green", finished_style="bold green"),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TextColumn("[dim]·[/dim]"),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            ) as progress:
                overall_task = progress.add_task(
                    "Processing symbols",
                    total=len(self.config.symbols),
                )
                phase_task = progress.add_task("", total=None, visible=False)
                stage_chain = self._stage_chain
                if stage_chain is None:
                    stage_chain = build_news_stage_chain(self)
                    self._stage_chain = stage_chain

                for symbol in self.config.symbols:
                    normalized_symbol = symbol.upper()
                    progress.update(
                        overall_task,
                        description=f"Processing {normalized_symbol}",
                    )

                    symbol_state = create_initial_news_state(
                        runtime=self,
                        symbol=normalized_symbol,
                        progress=progress,
                        phase_task=phase_task,
                    )
                    symbol_state = self.run_stage_chain(
                        initial_state=symbol_state,
                        stage_chain=stage_chain,
                    )

                    outputs.extend(symbol_state.outputs)
                    metadata[normalized_symbol] = symbol_state.metadata
                    items_fetched += len(symbol_state.fetched_items)
                    items_emitted += len(symbol_state.correlated_items)
                    clusters_detected += len(symbol_state.correlation.clusters)

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(
                success=True,
                metadata=coerce_result_json_dict(metadata),
            )
            return NewsResult(
                success=True,
                outputs=outputs,
                metadata=metadata,
                symbols_processed=len(self.config.symbols),
                items_fetched=items_fetched,
                items_emitted=items_emitted,
                clusters_detected=clusters_detected,
            )
        except Exception as exc:
            logger.exception("News pipeline failed")
            self.config.complete_run(success=False)
            return NewsResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        symbol: str,
        phase: str,
        *,
        total: int | None = None,
    ) -> None:
        """Update progress state and current news phase metadata."""
        if progress is None or phase_task is None:
            return

        if total is None:
            progress.reset(
                phase_task,
                start=True,
                description=f"  ├─ {symbol}: {phase}",
                visible=True,
                completed=0,
            )
            progress.update(
                phase_task,
                total=None,
                completed=0,
            )
        else:
            progress.reset(
                phase_task,
                start=True,
                description=f"  ├─ {symbol}: {phase}",
                visible=True,
                total=total,
                completed=0,
            )

    def _write_outputs(
        self,
        *,
        symbol: str,
        items: list[NewsHeadline],
        timeline: list[NewsTimelineEntry],
        correlation: NewsCorrelation,
        symbol_aliases: list[str],
    ) -> list[Path]:
        """Write news outputs and return emitted artifact paths."""
        symbol_out = self.config.get_symbol_output_dir(symbol)
        output_context = build_run_output_context(
            symbol=symbol,
            suffix="news",
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        base_stem = output_context.base_stem
        run_header = output_context.run_header
        run_short_id = output_context.run_short_id

        payload = NewsTimelinePayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            topics=self.config.topics,
            items=items,
            timeline=timeline,
            correlation=correlation,
            metadata={
                "days": self.config.days,
                "forms": self.config.forms or ["8-K", "10-K", "10-Q"],
                "feeds": self.config.feeds,
                "min_relevance": self.config.min_relevance,
                "require_symbol_match": self.config.require_symbol_match,
                "symbol_aliases": symbol_aliases,
                "max_results": self.config.max_results,
                "include_market_context": self.config.include_market_context,
            },
        )

        outputs: list[Path] = []
        if self.config.output_format in ("csv", "all"):
            csv_path = symbol_out / f"{base_stem}_timeline.csv"
            write_news_timeline_csv(
                csv_path,
                items,
                header_fields=run_header,
            )
            outputs.append(csv_path)

        if self.config.output_format in ("json", "all"):
            json_path = symbol_out / f"{base_stem}_summary.json"
            write_news_timeline_json(json_path, payload)
            outputs.append(json_path)

        if self.config.output_format in ("yaml", "all"):
            yaml_path = symbol_out / f"{base_stem}_summary.yaml"
            write_news_timeline_yaml(yaml_path, payload)
            outputs.append(yaml_path)

        return outputs
