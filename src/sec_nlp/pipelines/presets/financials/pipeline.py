"""Pipeline for extracting normalized financial statement data."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

from pydantic import PrivateAttr

from sec_nlp.core.edgar.xbrl_facts import XbrlParser, create_xbrl_parser
from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import build_run_file_stem
from sec_nlp.types import ResultDict

from .config import FinancialsSettings
from .io import (
    FinancialsOutputPayload,
    write_financials_csv,
    write_financials_json,
    write_financials_yaml,
)
from .models import FinancialsResult
from .steps import (
    aggregate_financials,
    build_delta_report,
    download_financial_filings,
    extract_financial_facts,
)


class FinancialsPipeline(BasePipeline):
    """Extract financial line items and derived ratios from filing XBRL."""

    pipeline_type: ClassVar[Literal["financials"]] = "financials"
    description: ClassVar[str] = (
        "Extract normalized financial statement line items from 10-K/10-Q XBRL"
    )
    requires_llm: ClassVar[bool] = False

    config: FinancialsSettings

    _parser: XbrlParser | None = PrivateAttr(default=None)

    @classmethod
    def config_model(cls) -> type[FinancialsSettings]:
        return FinancialsSettings

    @classmethod
    def result_model(cls) -> type[FinancialsResult]:
        return FinancialsResult

    def _build_components(self) -> None:
        self._parser = None

    def _get_parser(self) -> XbrlParser:
        if self._parser is None:
            self._parser = create_xbrl_parser()
        return self._parser

    def run(self) -> FinancialsResult:
        try:
            self.config.setup_paths()
            outputs: list[Path] = []
            metadata: ResultDict = {}
            periods_generated = 0

            for symbol in self.config.symbols:
                symbol_outputs, symbol_meta, symbol_periods = (
                    self._process_symbol(symbol.upper())
                )
                outputs.extend(symbol_outputs)
                metadata[symbol.upper()] = symbol_meta
                periods_generated += symbol_periods

            self.config.complete_run(success=True, metadata=metadata)
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

    def _process_symbol(
        self, symbol: str
    ) -> tuple[list[Path], dict[str, int | str], int]:
        filings = download_financial_filings(
            symbol=symbol, settings=self.config
        )
        parser = self._get_parser()

        all_facts = []
        for filing in filings:
            all_facts.extend(
                extract_financial_facts(
                    symbol=symbol, filing=filing, parser=parser
                )
            )

        statements = aggregate_financials(
            all_facts, compute_ratios=self.config.compute_ratios
        )
        delta_report = (
            build_delta_report(statements)
            if self.config.include_delta_report
            else {}
        )

        outputs = self._write_outputs(
            symbol=symbol,
            filings_processed=len(filings),
            statements=statements,
            delta_report=delta_report,
        )

        metadata = {
            "filings_processed": len(filings),
            "facts_extracted": len(all_facts),
            "periods_generated": len(statements),
        }
        return outputs, metadata, len(statements)

    def _write_outputs(
        self,
        *,
        symbol: str,
        filings_processed: int,
        statements,
        delta_report,
    ) -> list[Path]:
        symbol_out = self.config.get_symbol_output_dir(symbol)
        base_stem = build_run_file_stem(
            symbol, "financials", self.config.run_id
        )

        payload = FinancialsOutputPayload(
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
            write_financials_csv(csv_path, statements)
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
