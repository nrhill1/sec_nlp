# src/sec_nlp/pipelines/presets/holdings/pipeline.py
"""Institutional holdings analysis pipeline parsing 13F-HR filings.

Downloads quarterly 13F filings, parses XML holding tables, computes
quarter-over-quarter position diffs, aggregates sector and concentration
metrics, and exports snapshot and diff reports per filer.
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

from sec_nlp.core.edgar.holdings_parser import HoldingsParser
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.core.types import coerce_result_json_dict
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import build_run_output_context
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
from .run_stages import (
    HoldingsRunState,
    build_holdings_stage_chain,
)


class HoldingsPipeline(BasePipeline):
    """Parse 13F-HR filings into holdings snapshots with diff analysis.

    Downloads quarterly 13F filings, parses XML holding tables, computes
    position-level changes, and exports snapshot/diff reports per filer.
    """

    pipeline_type: ClassVar[Literal["holdings"]] = "holdings"
    description: ClassVar[str] = (
        "Analyze 13F holdings snapshots and quarter-over-quarter changes"
    )
    requires_llm: ClassVar[bool] = False

    config: HoldingsSettings

    _parser: HoldingsParser | None = PrivateAttr(default=None)
    _stage_chain: Runnable[HoldingsRunState, HoldingsRunState] | None = (
        PrivateAttr(default=None)
    )

    @classmethod
    def config_model(cls) -> type[HoldingsSettings]:
        return HoldingsSettings

    @classmethod
    def result_model(cls) -> type[HoldingsResult]:
        return HoldingsResult

    def _get_parser(self) -> HoldingsParser:
        """Get the filing parser instance used by the holdings pipeline."""
        if self._parser is None:
            self._parser = HoldingsParser()
        return self._parser

    def _build_components(self) -> None:
        """Initialize reusable components for holdings execution."""
        self._stage_chain = build_holdings_stage_chain(self)

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
                TextColumn("[bold #00d75f]{task.description}"),
                BarColumn(
                    complete_style="#00d75f", finished_style="bold #00ff87"
                ),
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
                stage_chain = self.require_stage_chain(self._stage_chain)

                for symbol in self.config.symbols:
                    normalized_symbol = symbol.upper()
                    progress.update(
                        overall_task,
                        description=f"Processing {normalized_symbol}",
                    )
                    symbol_state = HoldingsRunState(
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
                    total_positions += len(symbol_state.positions)
                    total_diffs += len(symbol_state.diffs)

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(
                success=True,
                metadata=coerce_result_json_dict(metadata),
            )
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

    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        symbol: str,
        phase: str,
        *,
        total: int | None = None,
    ) -> None:
        """Update progress state and current holdings phase metadata."""
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
        filings_processed: int,
        positions: list[HoldingPosition],
        diffs: list[HoldingsDiff],
        summary: OwnershipSummary,
    ) -> list[Path]:
        """Write holdings outputs and return artifact file paths."""
        symbol_out = self.config.get_symbol_output_dir(symbol)
        output_context = build_run_output_context(
            symbol=symbol,
            suffix="holdings",
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        base_stem = output_context.base_stem
        run_header = output_context.run_header
        run_short_id = output_context.run_short_id

        summary_payload = HoldingsSummaryPayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
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
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
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
