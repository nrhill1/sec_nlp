"""Pipeline for institutional holdings analysis from 13F filings."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

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

from sec_nlp.core.edgar.holdings_parser import HoldingsParser
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import (
    build_run_file_stem,
    build_run_header_fields,
)
from sec_nlp.types import ResultDict

from .config import HoldingsSettings
from .io import (
    HoldingsDiffPayload,
    HoldingsSummaryPayload,
    write_holdings_diff_json,
    write_holdings_diff_yaml,
    write_holdings_snapshot_csv,
    write_holdings_summary_json,
    write_holdings_summary_yaml,
)
from .models import (
    HoldingPosition,
    HoldingsDiff,
    HoldingsResult,
    OwnershipSummary,
)
from .steps import (
    build_holdings_diffs,
    build_ownership_summary,
    download_holdings_filings,
    parse_holding_positions,
)


class HoldingsPipeline(BasePipeline):
    """Analyze 13F holdings snapshots and quarter-over-quarter changes."""

    pipeline_type: ClassVar[Literal["holdings"]] = "holdings"
    description: ClassVar[str] = (
        "Analyze 13F holdings snapshots and quarter-over-quarter changes"
    )
    requires_llm: ClassVar[bool] = False

    config: HoldingsSettings

    _parser: HoldingsParser | None = PrivateAttr(default=None)

    @classmethod
    def config_model(cls) -> type[HoldingsSettings]:
        return HoldingsSettings

    @classmethod
    def result_model(cls) -> type[HoldingsResult]:
        return HoldingsResult

    def _build_components(self) -> None:
        self._parser = None

    def _get_parser(self) -> HoldingsParser:
        if self._parser is None:
            self._parser = HoldingsParser()
        return self._parser

    def run(self) -> HoldingsResult:
        try:
            self.config.setup_paths()
            outputs: list[Path] = []
            metadata: ResultDict = {}
            total_positions = 0
            total_diffs = 0

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
                        positions_count,
                        diffs_count,
                    ) = self._process_symbol(
                        normalized_symbol,
                        progress=progress,
                        phase_task=phase_task,
                    )
                    outputs.extend(symbol_outputs)
                    metadata[normalized_symbol] = symbol_meta
                    total_positions += positions_count
                    total_diffs += diffs_count

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(success=True, metadata=metadata)
            return HoldingsResult(
                success=True,
                outputs=outputs,
                metadata=metadata,
                symbols_processed=len(self.config.symbols),
                positions_processed=total_positions,
                diffs_generated=total_diffs,
            )
        except Exception as exc:
            logger.exception("Holdings pipeline failed")
            self.config.complete_run(success=False)
            return HoldingsResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _process_symbol(
        self,
        symbol: str,
        *,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> tuple[list[Path], dict[str, int | float | str | None], int, int]:
        self._update_phase(progress, phase_task, symbol, "Downloading")
        filings = download_holdings_filings(symbol=symbol, settings=self.config)
        parser = self._get_parser()

        self._update_phase(
            progress,
            phase_task,
            symbol,
            "Parsing",
            total=len(filings),
        )
        positions: list[HoldingPosition] = []
        for filing in filings:
            positions.extend(
                parse_holding_positions(
                    symbol=symbol,
                    filing=filing,
                    parser=parser,
                    cusip_filter=self.config.cusip,
                )
            )
            if progress is not None and phase_task is not None:
                progress.advance(phase_task)

        self._update_phase(progress, phase_task, symbol, "Diffing")
        diffs = build_holdings_diffs(symbol=symbol, positions=positions)
        self._update_phase(progress, phase_task, symbol, "Aggregating")
        summary = build_ownership_summary(
            symbol=symbol,
            positions=positions,
            top_holders=self.config.top_holders,
            cusip_filter=self.config.cusip,
        )

        self._update_phase(progress, phase_task, symbol, "Writing")
        outputs = self._write_outputs(
            symbol=symbol,
            filings_processed=len(filings),
            positions=positions,
            diffs=diffs,
            summary=summary,
        )

        metadata: dict[str, int | float | str | None] = {
            "filings_processed": len(filings),
            "positions_processed": len(positions),
            "diffs_generated": len(diffs),
            "latest_accession": summary.latest_accession,
            "total_value_thousands": summary.total_value_thousands,
            "concentration_hhi": summary.concentration_hhi,
            "filtered_positions": summary.filtered_positions,
        }

        return outputs, metadata, len(positions), len(diffs)

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
        update_kwargs: dict[str, str | int | bool | None] = {
            "description": f"  ├─ {symbol}: {phase}",
            "visible": True,
        }
        if total is None:
            update_kwargs["total"] = None
            update_kwargs["completed"] = 0
        else:
            update_kwargs["total"] = total
            update_kwargs["completed"] = 0
        progress.update(phase_task, **update_kwargs)

    def _write_outputs(
        self,
        *,
        symbol: str,
        filings_processed: int,
        positions: list[HoldingPosition],
        diffs: list[HoldingsDiff],
        summary: OwnershipSummary,
    ) -> list[Path]:
        symbol_out = self.config.get_symbol_output_dir(symbol)
        base_stem = build_run_file_stem(symbol, "holdings", self.config.run_id)
        run_header = build_run_header_fields(
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )

        summary_payload = HoldingsSummaryPayload(
            **run_header,
            symbol=symbol,
            filings_processed=filings_processed,
            positions=positions,
            summary=summary,
            metadata={
                "forms": self.config.forms or ["13F-HR", "13F-HR/A"],
                "quarters": self.config.quarters,
                "top_holders": self.config.top_holders,
                "cusip_filter": self.config.cusip,
            },
        )
        diff_payload = HoldingsDiffPayload(
            **run_header,
            symbol=symbol,
            diffs=diffs,
        )

        outputs: list[Path] = []
        if self.config.output_format in ("csv", "all"):
            snapshot_path = symbol_out / f"{base_stem}_snapshot.csv"
            write_holdings_snapshot_csv(
                snapshot_path,
                positions,
                header_fields=run_header,
            )
            outputs.append(snapshot_path)
        if self.config.output_format in ("json", "all"):
            summary_json_path = symbol_out / f"{base_stem}_summary.json"
            diff_json_path = symbol_out / f"{base_stem}_diff.json"
            write_holdings_summary_json(summary_json_path, summary_payload)
            write_holdings_diff_json(diff_json_path, diff_payload)
            outputs.extend([summary_json_path, diff_json_path])
        if self.config.output_format in ("yaml", "all"):
            summary_yaml_path = symbol_out / f"{base_stem}_summary.yaml"
            diff_yaml_path = symbol_out / f"{base_stem}_diff.yaml"
            write_holdings_summary_yaml(summary_yaml_path, summary_payload)
            write_holdings_diff_yaml(diff_yaml_path, diff_payload)
            outputs.extend([summary_yaml_path, diff_yaml_path])

        return outputs
