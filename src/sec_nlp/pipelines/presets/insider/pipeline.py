"""Pipeline for insider transaction analysis from Forms 3/4/5."""

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

from sec_nlp.core.edgar.insider_parser import InsiderParser
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import build_run_file_stem
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
from .steps import (
    TradeCluster,
    build_insider_ledgers,
    compute_net_buy_ratio,
    correlate_insider_activity,
    download_insider_filings,
    find_trade_clusters,
    parse_insider_transactions,
)


class InsiderPipeline(BasePipeline):
    """Analyze insider ownership filings and emit ledger/alert outputs."""

    pipeline_type: ClassVar[Literal["insider"]] = "insider"
    description: ClassVar[str] = (
        "Analyze insider Form 3/4/5 transactions and flag suspicious activity"
    )
    requires_llm: ClassVar[bool] = False

    config: InsiderSettings

    _parser: InsiderParser | None = PrivateAttr(default=None)

    @classmethod
    def config_model(cls) -> type[InsiderSettings]:
        return InsiderSettings

    @classmethod
    def result_model(cls) -> type[InsiderResult]:
        return InsiderResult

    def _build_components(self) -> None:
        self._parser = None

    def _get_parser(self) -> InsiderParser:
        if self._parser is None:
            self._parser = InsiderParser()
        return self._parser

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

                for symbol in self.config.symbols:
                    normalized_symbol = symbol.upper()
                    progress.update(
                        overall_task,
                        description=f"Processing {normalized_symbol}",
                    )

                    symbol_outputs, symbol_meta, tx_count, alert_count = (
                        self._process_symbol(
                            normalized_symbol,
                            progress=progress,
                            phase_task=phase_task,
                        )
                    )

                    outputs.extend(symbol_outputs)
                    metadata[normalized_symbol] = symbol_meta
                    total_transactions += tx_count
                    total_alerts += alert_count

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(success=True, metadata=metadata)
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

    def _process_symbol(
        self,
        symbol: str,
        *,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> tuple[list[Path], dict[str, int | float | str | None], int, int]:
        self._update_phase(progress, phase_task, symbol, "Downloading")
        filings = download_insider_filings(symbol=symbol, settings=self.config)
        parser = self._get_parser()

        self._update_phase(
            progress,
            phase_task,
            symbol,
            "Parsing",
            total=len(filings),
        )
        transactions: list[InsiderTransaction] = []
        for filing in filings:
            transactions.extend(
                parse_insider_transactions(
                    symbol=symbol,
                    filing=filing,
                    parser=parser,
                )
            )
            if progress is not None and phase_task is not None:
                progress.advance(phase_task)

        self._update_phase(progress, phase_task, symbol, "Aggregating")
        ledgers = build_insider_ledgers(transactions)
        clusters = find_trade_clusters(
            transactions,
            window_days=self.config.alert_window_days,
            cluster_threshold=self.config.alert_cluster_threshold,
        )
        net_buy_ratio = compute_net_buy_ratio(transactions)

        self._update_phase(progress, phase_task, symbol, "Correlating")
        alerts, correlation_meta = correlate_insider_activity(
            symbol=symbol,
            transactions=transactions,
            clusters=clusters,
            settings=self.config,
        )

        self._update_phase(progress, phase_task, symbol, "Writing")
        outputs = self._write_outputs(
            symbol=symbol,
            filings_processed=len(filings),
            transactions=transactions,
            ledgers=ledgers,
            alerts=alerts,
            net_buy_ratio=net_buy_ratio,
            clusters=clusters,
            correlation_meta=correlation_meta,
        )

        metadata: dict[str, int | float | str | None] = {
            "filings_processed": len(filings),
            "transactions_processed": len(transactions),
            "ledger_rows": len(ledgers),
            "clusters_detected": len(clusters),
            "alerts_generated": len(alerts),
            "net_buy_ratio": net_buy_ratio,
            "material_filings_considered": int(
                correlation_meta.get("material_filings_considered", 0)
            ),
            "market_windows_evaluated": int(
                correlation_meta.get("market_windows_evaluated", 0)
            ),
        }

        return outputs, metadata, len(transactions), len(alerts)

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
        transactions: list[InsiderTransaction],
        ledgers: list[InsiderLedger],
        alerts: list[InsiderAlert],
        net_buy_ratio: float | None,
        clusters: list[TradeCluster],
        correlation_meta: dict[str, int],
    ) -> list[Path]:
        symbol_out = self.config.get_symbol_output_dir(symbol)
        base_stem = build_run_file_stem(symbol, "insider", self.config.run_id)

        summary_payload = InsiderSummaryPayload(
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
        alerts_payload = InsiderAlertsPayload(symbol=symbol, alerts=alerts)

        outputs: list[Path] = []

        if self.config.output_format in ("csv", "all"):
            ledger_path = symbol_out / f"{base_stem}_ledger.csv"
            write_insider_ledger_csv(ledger_path, transactions)
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
