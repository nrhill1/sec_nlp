# src/sec_nlp/pipelines/presets/events/pipeline.py
"""Event detection and timeline scoring pipeline for current-report filings.

Scans 8-K and 6-K filings per symbol, classifies event types (e.g.
acquisition, leadership change, material agreement), scores significance,
and produces chronological timelines exported as YAML/CSV.
"""

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

from .config import EventsSettings
from .io import (
    EventsTimelinePayload,
    write_events_timeline_csv,
    write_events_timeline_json,
    write_events_timeline_yaml,
)
from .models import DetectedEvent, EventsResult
from .run_stages import (
    EventsRunState,
    build_events_stage_chain,
)


class EventsPipeline(BasePipeline):
    """Detect and score material events from current-report filings.

    Downloads 8-K/6-K filings, classifies each into event categories,
    enriches with market-impact scoring, and exports a chronological
    timeline per symbol.
    """

    pipeline_type: ClassVar[Literal["events"]] = "events"
    description: ClassVar[str] = (
        "Detect material events from 8-K/6-K filings and score market impact"
    )
    requires_llm: ClassVar[bool] = False

    config: EventsSettings
    _stage_chain: Runnable[EventsRunState, EventsRunState] | None = PrivateAttr(
        default=None
    )

    @classmethod
    def config_model(cls) -> type[EventsSettings]:
        return EventsSettings

    @classmethod
    def result_model(cls) -> type[EventsResult]:
        return EventsResult

    def _build_components(self) -> None:
        """Initialize reusable components for events pipeline execution."""
        self._stage_chain = build_events_stage_chain(self)

    def run(self) -> EventsResult:
        try:
            self.config.setup_paths()
            outputs: list[Path] = []
            metadata: ResultDict = {}
            total_detected = 0
            total_scored = 0
            total_headlines = 0

            console = get_rich_console()
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(complete_style="green", finished_style="bold green"),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TextColumn("[dim]-[/dim]"),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            ) as progress:
                overall_task = progress.add_task(
                    "Processing symbols",
                    total=len(self.config.symbols),
                )
                phase_task = progress.add_task("", total=None, visible=False)
                stage_chain = self.require_stage_chain(self._stage_chain)

                for symbol in self.config.symbols:
                    normalized_symbol = symbol.upper()
                    progress.update(
                        overall_task,
                        description=f"Processing {normalized_symbol}",
                    )

                    symbol_state = EventsRunState(
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
                    total_detected += len(symbol_state.scored_events)
                    total_scored += symbol_state.scored_count
                    total_headlines += symbol_state.headlines_linked

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(
                success=True,
                metadata=coerce_result_json_dict(metadata),
            )
            return EventsResult(
                success=True,
                outputs=outputs,
                metadata=metadata,
                symbols_processed=len(self.config.symbols),
                events_detected=total_detected,
                events_scored=total_scored,
                headlines_linked=total_headlines,
            )
        except Exception as exc:
            logger.exception("Events pipeline failed")
            self.config.complete_run(success=False)
            return EventsResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        symbol: str,
        phase: str,
    ) -> None:
        """Update progress state and current events phase metadata."""
        if progress is None or phase_task is None:
            return

        progress.reset(
            phase_task,
            start=True,
            description=f"  - {symbol}: {phase}",
            visible=True,
            completed=0,
        )
        progress.update(
            phase_task,
            total=None,
            completed=0,
        )

    def _write_outputs(
        self,
        *,
        symbol: str,
        events: list[DetectedEvent],
    ) -> list[Path]:
        """Write events outputs and return emitted artifact paths."""
        symbol_out = self.config.get_symbol_output_dir(symbol)
        output_context = build_run_output_context(
            symbol=symbol,
            suffix="events",
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        base_stem = output_context.base_stem
        run_header = output_context.run_header
        run_short_id = output_context.run_short_id

        payload = EventsTimelinePayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            events=events,
            metadata={
                "forms": self.config.effective_forms,
                "lookback_years": self.config.lookback_years,
                "event_types": self.config.event_types,
                "pre_window_days": self.config.pre_window_days,
                "post_window_days": self.config.post_window_days,
                "news_window_days": self.config.news_window_days,
                "max_headlines_per_event": self.config.max_headlines_per_event,
                "benchmark_symbol": self.config.benchmark_symbol,
                "significance_threshold": self.config.significance_threshold,
            },
        )

        outputs: list[Path] = []
        if self.config.output_format in ("csv", "all"):
            csv_path = symbol_out / f"{base_stem}_timeline.csv"
            write_events_timeline_csv(
                csv_path,
                events,
                header_fields=run_header,
            )
            outputs.append(csv_path)

        if self.config.output_format in ("json", "all"):
            json_path = symbol_out / f"{base_stem}_summary.json"
            write_events_timeline_json(json_path, payload)
            outputs.append(json_path)

        if self.config.output_format in ("yaml", "all"):
            yaml_path = symbol_out / f"{base_stem}_summary.yaml"
            write_events_timeline_yaml(yaml_path, payload)
            outputs.append(yaml_path)

        return outputs
