# src/sec_nlp/pipelines/presets/financials/pipeline.py
"""Financial statement extraction pipeline using XBRL fact parsing.

Downloads annual/quarterly filings, extracts XBRL facts via the Rust
extension, normalizes line items into a canonical schema, computes
derived ratios, and exports per-symbol CSV/JSON statement files.
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

from sec_nlp.core.edgar.xbrl_facts import XbrlParser, create_xbrl_parser
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.core.types import coerce_result_json_dict
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import build_run_output_context
from sec_nlp.types import ResultDict

from .config import FinancialsSettings
from .io import (
    FinancialsOutputPayload,
    write_financials_csv,
    write_financials_json,
    write_financials_yaml,
)
from .models import FinancialsResult
from .run_stages import (
    FinancialsRunState,
    build_financials_stage_chain,
)


class FinancialsPipeline(BasePipeline):
    """Extract and normalize financial statements from XBRL-tagged filings.

    Parses XBRL facts via the Rust extension, maps them to a canonical
    line-item schema, computes derived financial ratios, and exports
    per-symbol statement files.
    """

    pipeline_type: ClassVar[Literal["financials"]] = "financials"
    description: ClassVar[str] = (
        "Extract normalized financial statement line items from 10-K/10-Q XBRL"
    )
    requires_llm: ClassVar[bool] = False

    config: FinancialsSettings

    _parser: XbrlParser | None = PrivateAttr(default=None)
    _stage_chain: Runnable[FinancialsRunState, FinancialsRunState] | None = (
        PrivateAttr(default=None)
    )

    @classmethod
    def config_model(cls) -> type[FinancialsSettings]:
        return FinancialsSettings

    @classmethod
    def result_model(cls) -> type[FinancialsResult]:
        return FinancialsResult

    def _get_parser(self) -> XbrlParser:
        """Get the filing parser instance used by the financials pipeline."""
        if self._parser is None:
            self._parser = create_xbrl_parser()
        return self._parser

    def _build_components(self) -> None:
        """Initialize reusable components for financials execution."""
        self._stage_chain = build_financials_stage_chain(self)

    def run(self) -> FinancialsResult:
        try:
            self.config.setup_paths()
            outputs: list[Path] = []
            metadata: ResultDict = {}
            periods_generated = 0

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

                    symbol_state = FinancialsRunState(
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
                    periods_generated += len(symbol_state.statements)

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(
                success=True,
                metadata=coerce_result_json_dict(metadata),
            )
            return FinancialsResult(
                success=True,
                outputs=outputs,
                metadata=metadata,
                symbols_processed=len(self.config.symbols),
                periods_generated=periods_generated,
            )
        except Exception as exc:
            logger.exception("Financials pipeline failed")
            self.config.complete_run(success=False)
            return FinancialsResult(
                success=False, error=f"{type(exc).__name__}: {exc}"
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
        """Update progress state and current financials phase metadata."""
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
        statements,
        delta_report,
    ) -> list[Path]:
        """Write financials outputs and return artifact file paths."""
        symbol_out = self.config.get_symbol_output_dir(symbol)
        output_context = build_run_output_context(
            symbol=symbol,
            suffix="financials",
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        base_stem = output_context.base_stem
        run_header = output_context.run_header
        run_short_id = output_context.run_short_id

        payload = FinancialsOutputPayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            filings_processed=filings_processed,
            periods=statements,
            delta_report=delta_report,
            metadata={
                "form_types": self.config.form_types,
                "compute_ratios": self.config.compute_ratios,
            },
        )

        outputs: list[Path] = []
        if self.config.output_format in ("csv", "all"):
            csv_path = symbol_out / f"{base_stem}.csv"
            write_financials_csv(
                csv_path,
                statements,
                header_fields=run_header,
            )
            outputs.append(csv_path)
        if self.config.output_format in ("json", "all"):
            json_path = symbol_out / f"{base_stem}.json"
            write_financials_json(json_path, payload)
            outputs.append(json_path)
        if self.config.output_format in ("yaml", "all"):
            yaml_path = symbol_out / f"{base_stem}.yaml"
            write_financials_yaml(yaml_path, payload)
            outputs.append(yaml_path)

        return outputs
