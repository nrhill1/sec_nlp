"""Pipeline for event detection and timeline scoring."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal, cast

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
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import (
    build_run_file_stem,
    build_run_header_fields,
)
from sec_nlp.types import JsonDict, ResultDict

from .config import EventsSettings
from .io import (
    EventsTimelinePayload,
    write_events_timeline_csv,
    write_events_timeline_json,
    write_events_timeline_yaml,
)
from .models import DetectedEvent, EventsResult
from .steps import (
    enrich_events_with_news,
    scan_events_for_symbol,
    score_event_impacts,
)


class EventsPipeline(BasePipeline):
    """Detect events from 8-K filings and produce a scored timeline."""

    pipeline_type: ClassVar[Literal["events"]] = "events"
    description: ClassVar[str] = (
        "Detect material events from 8-K filings and score market impact"
    )
    requires_llm: ClassVar[bool] = False

    config: EventsSettings

    @classmethod
    def config_model(cls) -> type[EventsSettings]:
        return EventsSettings

    @classmethod
    def result_model(cls) -> type[EventsResult]:
        return EventsResult

    def _build_components(self) -> None:
        return

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

                for symbol in self.config.symbols:
                    normalized_symbol = symbol.upper()
                    progress.update(
                        overall_task,
                        description=f"Processing {normalized_symbol}",
                    )

                    (
                        symbol_outputs,
                        symbol_meta,
                        detected_count,
                        scored_count,
                        headline_count,
                    ) = self._process_symbol(
                        normalized_symbol,
                        progress=progress,
                        phase_task=phase_task,
                    )

                    outputs.extend(symbol_outputs)
                    metadata[normalized_symbol] = symbol_meta
                    total_detected += detected_count
                    total_scored += scored_count
                    total_headlines += headline_count

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(
                success=True,
                metadata=cast(JsonDict, metadata),
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

    def _process_symbol(
        self,
        symbol: str,
        *,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> tuple[list[Path], dict[str, int | float | str | None], int, int, int]:
        self._update_phase(progress, phase_task, symbol, "Scanning")
        scanned_events, downloaded, filings_scanned = scan_events_for_symbol(
            symbol=symbol,
            settings=self.config,
        )

        self._update_phase(progress, phase_task, symbol, "Enriching")
        enriched_events, headlines_linked = enrich_events_with_news(
            symbol=symbol,
            events=scanned_events,
            settings=self.config,
        )

        self._update_phase(progress, phase_task, symbol, "Scoring")
        scored_events, scored_count = score_event_impacts(
            symbol=symbol,
            events=enriched_events,
            settings=self.config,
        )

        self._update_phase(progress, phase_task, symbol, "Writing")
        outputs = self._write_outputs(symbol=symbol, events=scored_events)

        metadata: dict[str, int | float | str | None] = {
            "downloaded": downloaded,
            "filings_scanned": filings_scanned,
            "events_detected": len(scored_events),
            "events_scored": scored_count,
            "headlines_linked": headlines_linked,
        }

        return (
            outputs,
            metadata,
            len(scored_events),
            scored_count,
            headlines_linked,
        )

    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        symbol: str,
        phase: str,
    ) -> None:
        if progress is None or phase_task is None:
            return

        progress.update(
            phase_task,
            description=f"  - {symbol}: {phase}",
            visible=True,
            total=None,
            completed=0,
        )

    def _write_outputs(
        self,
        *,
        symbol: str,
        events: list[DetectedEvent],
    ) -> list[Path]:
        symbol_out = self.config.get_symbol_output_dir(symbol)
        base_stem = build_run_file_stem(symbol, "events", self.config.run_id)
        run_header = build_run_header_fields(
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        run_short_id_raw = run_header.get("run_short_id")
        run_short_id = (
            run_short_id_raw if isinstance(run_short_id_raw, int) else None
        )

        payload = EventsTimelinePayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            events=events,
            metadata={
                "forms": self.config.forms or ["8-K"],
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
