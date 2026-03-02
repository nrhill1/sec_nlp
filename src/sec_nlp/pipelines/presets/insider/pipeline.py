# src/sec_nlp/pipelines/presets/insider/pipeline.py
"""Pipeline for insider transaction analysis from Forms 3/4/5."""

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

from sec_nlp.core.edgar.insider_parser import InsiderParser
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.core.types import coerce_result_json_dict
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import build_run_output_context
from sec_nlp.types import ResultDict

from .config import InsiderSettings
from .io import (
    InsiderAlertsPayload,
    InsiderSummaryPayload,
    write_insider_alerts_json,
    write_insider_alerts_yaml,
    write_insider_ledger_csv,
    write_insider_summary_json,
    write_insider_summary_yaml,
)
from .models import (
    InsiderAlert,
    InsiderLedger,
    InsiderResult,
    InsiderTransaction,
)
from .run_stages import (
    InsiderRunState,
    build_insider_stage_chain,
)
from .steps import TradeCluster


class InsiderPipeline(BasePipeline):
    """Analyze insider ownership filings and emit ledger/alert outputs."""

    pipeline_type: ClassVar[Literal["insider"]] = "insider"
    description: ClassVar[str] = (
        "Analyze insider Form 3/4/5 transactions and flag suspicious activity"
    )
    requires_llm: ClassVar[bool] = False

    config: InsiderSettings

    _parser: InsiderParser | None = PrivateAttr(default=None)
    _stage_chain: Runnable[InsiderRunState, InsiderRunState] | None = (
        PrivateAttr(default=None)
    )

    @classmethod
    def config_model(cls) -> type[InsiderSettings]:
        return InsiderSettings

    @classmethod
    def result_model(cls) -> type[InsiderResult]:
        return InsiderResult

    def _get_parser(self) -> InsiderParser:
        """Get the filing parser instance used by the insider pipeline."""
        if self._parser is None:
            self._parser = InsiderParser()
        return self._parser

    def _build_components(self) -> None:
        """Initialize reusable components for insider execution."""
        self._stage_chain = build_insider_stage_chain(self)

    def run(self) -> InsiderResult:
        try:
            self.config.setup_paths()
            outputs: list[Path] = []
            metadata: ResultDict = {}
            total_transactions = 0
            total_alerts = 0

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
                stage_chain = self.require_stage_chain(self._stage_chain)

                for symbol in self.config.symbols:
                    normalized_symbol = symbol.upper()
                    progress.update(
                        overall_task,
                        description=f"Processing {normalized_symbol}",
                    )

                    symbol_state = InsiderRunState(
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
                    total_transactions += len(symbol_state.transactions)
                    total_alerts += len(symbol_state.alerts)

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(
                success=True,
                metadata=coerce_result_json_dict(metadata),
            )
            return InsiderResult(
                success=True,
                outputs=outputs,
                metadata=metadata,
                symbols_processed=len(self.config.symbols),
                transactions_processed=total_transactions,
                alerts_generated=total_alerts,
            )
        except Exception as exc:
            logger.exception("Insider pipeline failed")
            self.config.complete_run(success=False)
            return InsiderResult(
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
        """Update progress state and current insider phase metadata."""
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
        transactions: list[InsiderTransaction],
        ledgers: list[InsiderLedger],
        alerts: list[InsiderAlert],
        net_buy_ratio: float | None,
        clusters: list[TradeCluster],
        correlation_meta: dict[str, int],
    ) -> list[Path]:
        """Write insider outputs and return artifact file paths."""
        symbol_out = self.config.get_symbol_output_dir(symbol)
        output_context = build_run_output_context(
            symbol=symbol,
            suffix="insider",
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        base_stem = output_context.base_stem
        run_header = output_context.run_header
        run_short_id = output_context.run_short_id

        summary_payload = InsiderSummaryPayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            filings_processed=filings_processed,
            transactions=transactions,
            ledgers=ledgers,
            net_buy_ratio=net_buy_ratio,
            metadata={
                "forms": self.config.forms or ["3", "4", "5"],
                "lookback_months": self.config.lookback_months,
                "clusters_detected": len(clusters),
                **correlation_meta,
            },
        )
        alerts_payload = InsiderAlertsPayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            alerts=alerts,
        )

        outputs: list[Path] = []

        if self.config.output_format in ("csv", "all"):
            ledger_path = symbol_out / f"{base_stem}_ledger.csv"
            write_insider_ledger_csv(
                ledger_path,
                transactions,
                header_fields=run_header,
            )
            outputs.append(ledger_path)

        if self.config.output_format in ("json", "all"):
            summary_json_path = symbol_out / f"{base_stem}_summary.json"
            alerts_json_path = symbol_out / f"{base_stem}_alerts.json"
            write_insider_summary_json(summary_json_path, summary_payload)
            write_insider_alerts_json(alerts_json_path, alerts_payload)
            outputs.extend([summary_json_path, alerts_json_path])

        if self.config.output_format in ("yaml", "all"):
            summary_yaml_path = symbol_out / f"{base_stem}_summary.yaml"
            alerts_yaml_path = symbol_out / f"{base_stem}_alerts.yaml"
            write_insider_summary_yaml(summary_yaml_path, summary_payload)
            write_insider_alerts_yaml(alerts_yaml_path, alerts_payload)
            outputs.extend([summary_yaml_path, alerts_yaml_path])

        return outputs
