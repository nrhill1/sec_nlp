# src/sec_nlp/pipelines/presets/analyze/io/result_writer.py
"""Output writing helpers for the analyze pipeline."""

from __future__ import annotations

from pathlib import Path

from sec_nlp.pipelines.metadata.accession import (
    get_accession_from_metadata,
    group_results_by_accession,
)
from sec_nlp.pipelines.presets.analyze.market import MarketEnrichment
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord

from ..config import AnalyzeConfig
from ..types import Timings
from ..utils import resolve_symbol_for_output
from .outputs import OutputFormatter


def write_results(
    *,
    config: AnalyzeConfig,
    formatter: OutputFormatter,
    symbol: str,
    filing_meta: MetadataRecord,
    analysis_results: list[AnalysisResultDict],
    relevant_results: list[AnalysisResultDict] | None = None,
    search_queries: list[str] | None = None,
    timings: Timings | None = None,
    market_data: MarketEnrichment | None = None,
) -> list[Path]:
    """Write analysis results to output files."""
    output_files: list[Path] = []

    if relevant_results is None:
        relevant_results = [
            r for r in analysis_results if formatter.is_relevant_result(r)
        ]

    grouped_all = group_results_by_accession(analysis_results, filing_meta)
    grouped_relevant = group_results_by_accession(relevant_results, filing_meta)

    if config.aggregate_by_filing:
        if grouped_relevant:
            for accession, results_for_filing in grouped_relevant.items():
                all_for_filing = grouped_all.get(accession, [])
                meta = _select_filing_meta(
                    results_for_filing,
                    filing_meta,
                    accession,
                )
                first_source_meta = next(
                    (
                        r.get("source_metadata")
                        for r in results_for_filing
                        if r.get("source_metadata")
                    ),
                    None,
                )
                symbol_for_output = resolve_symbol_for_output(
                    symbol, meta, first_source_meta
                )
                output = formatter.build_output(
                    symbol=symbol_for_output,
                    filing_meta=meta,
                    analysis_results=all_for_filing,
                    relevant_results=results_for_filing,
                    search_queries=search_queries,
                    timings=timings,
                    market_data=market_data,
                )
                output_dir = config.get_symbol_output_dir(symbol_for_output)
                output_files.extend(
                    formatter.export(output, output_dir, accession)
                )
        else:
            accession = get_accession_from_metadata(filing_meta)
            symbol_for_output = resolve_symbol_for_output(symbol, filing_meta)
            output = formatter.build_output(
                symbol=symbol_for_output,
                filing_meta=filing_meta,
                analysis_results=analysis_results,
                relevant_results=[],
                search_queries=search_queries,
                timings=timings,
                market_data=market_data,
            )
            output_dir = config.get_symbol_output_dir(symbol_for_output)
            output_files.extend(formatter.export(output, output_dir, accession))
    else:
        accession = get_accession_from_metadata(filing_meta)
        first_meta = next(
            (
                r.get("source_metadata")
                for r in (relevant_results or [])
                if r.get("source_metadata")
            ),
            None,
        ) or next(
            (
                r.get("source_metadata")
                for r in (analysis_results or [])
                if r.get("source_metadata")
            ),
            None,
        )
        symbol_for_output = resolve_symbol_for_output(
            symbol, filing_meta, first_meta
        )
        output = formatter.build_output(
            symbol=symbol_for_output,
            filing_meta=filing_meta,
            analysis_results=analysis_results,
            relevant_results=relevant_results,
            search_queries=search_queries,
            timings=timings,
            market_data=market_data,
        )
        output_dir = config.get_symbol_output_dir(symbol_for_output)
        output_files.extend(formatter.export(output, output_dir, accession))

    return output_files


def _select_filing_meta(
    results_for_filing: list[AnalysisResultDict],
    fallback_meta: MetadataRecord,
    accession: str,
) -> MetadataRecord:
    """Pick the best metadata source for a filing."""
    if results_for_filing:
        meta: MetadataRecord = (
            results_for_filing[0].get("source_metadata") or {}
        )
    else:
        meta = {}

    merged_meta: MetadataRecord = {**fallback_meta, **meta}
    if accession and merged_meta.get("accession_number") is None:
        merged_meta["accession_number"] = accession

    return merged_meta
