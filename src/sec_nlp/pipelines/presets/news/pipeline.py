"""Pipeline for monitoring company-centric financial news."""

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

from .config import NewsSettings
from .io import (
    NewsTimelinePayload,
    write_news_timeline_csv,
    write_news_timeline_json,
    write_news_timeline_yaml,
)
from .models import NewsCorrelation, NewsHeadline, NewsResult, NewsTimelineEntry
from .steps import (
    correlate_news_items,
    fetch_news_items,
    match_news_items,
    resolve_symbol_aliases,
)


class NewsPipeline(BasePipeline):
    """Fetch, score, correlate, and export financial news timelines."""

    pipeline_type: ClassVar[Literal["news"]] = "news"
    description: ClassVar[str] = (
        "Monitor financial news, score topic relevance, and correlate with filings and market moves"
    )
    requires_llm: ClassVar[bool] = False

    config: NewsSettings

    @classmethod
    def config_model(cls) -> type[NewsSettings]:
        return NewsSettings

    @classmethod
    def result_model(cls) -> type[NewsResult]:
        return NewsResult

    def _build_components(self) -> None:
        return

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

                for symbol in self.config.symbols:
                    normalized_symbol = symbol.upper()
                    progress.update(
                        overall_task,
                        description=f"Processing {normalized_symbol}",
                    )

                    (
                        symbol_outputs,
                        symbol_meta,
                        fetched_count,
                        emitted_count,
                        cluster_count,
                    ) = self._process_symbol(
                        normalized_symbol,
                        progress=progress,
                        phase_task=phase_task,
                    )

                    outputs.extend(symbol_outputs)
                    metadata[normalized_symbol] = symbol_meta
                    items_fetched += fetched_count
                    items_emitted += emitted_count
                    clusters_detected += cluster_count

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(
                success=True,
                metadata=cast(JsonDict, metadata),
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

    def _process_symbol(
        self,
        symbol: str,
        *,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> tuple[list[Path], dict[str, int | float | str | None], int, int, int]:
        symbol_aliases = resolve_symbol_aliases(
            symbol=symbol,
            settings=self.config,
        )

        self._update_phase(progress, phase_task, symbol, "Fetching")
        fetched_items = fetch_news_items(symbol=symbol, settings=self.config)

        self._update_phase(progress, phase_task, symbol, "Matching")
        matched_items = match_news_items(
            items=fetched_items,
            symbol=symbol,
            topics=self.config.topics,
            min_relevance=self.config.min_relevance,
            require_symbol_match=self.config.require_symbol_match,
            symbol_aliases=symbol_aliases,
        )

        self._update_phase(progress, phase_task, symbol, "Correlating")
        correlated_items, timeline, correlation = correlate_news_items(
            symbol=symbol,
            items=matched_items,
            settings=self.config,
        )

        self._update_phase(progress, phase_task, symbol, "Writing")
        outputs = self._write_outputs(
            symbol=symbol,
            items=correlated_items,
            timeline=timeline,
            correlation=correlation,
            symbol_aliases=symbol_aliases,
        )

        metadata: dict[str, int | float | str | None] = {
            "items_fetched": len(fetched_items),
            "items_emitted": len(correlated_items),
            "timeline_days": len(timeline),
            "days_compared": correlation.days_compared,
            "news_to_return_correlation": correlation.news_to_return_correlation,
            "filings_linked": correlation.filings_linked,
            "clusters_detected": len(correlation.clusters),
            "symbol_alias_count": len(symbol_aliases),
        }

        return (
            outputs,
            metadata,
            len(fetched_items),
            len(correlated_items),
            len(correlation.clusters),
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
        if progress is None or phase_task is None:
            return

        if total is None:
            progress.update(
                phase_task,
                description=f"  ├─ {symbol}: {phase}",
                visible=True,
                total=None,
                completed=0,
            )
        else:
            progress.update(
                phase_task,
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
        symbol_out = self.config.get_symbol_output_dir(symbol)
        base_stem = build_run_file_stem(symbol, "news", self.config.run_id)
        run_header = build_run_header_fields(
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        run_short_id_raw = run_header.get("run_short_id")
        run_short_id = (
            run_short_id_raw if isinstance(run_short_id_raw, int) else None
        )

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
