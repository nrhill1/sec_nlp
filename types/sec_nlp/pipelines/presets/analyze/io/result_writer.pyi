from pathlib import Path

from sec_nlp.pipelines.runtime import (
    get_accession_from_metadata as get_accession_from_metadata,
    group_results_by_accession as group_results_by_accession,
)
from sec_nlp.pipelines.types import (
    AnalysisResultDict as AnalysisResultDict,
    MetadataRecord as MetadataRecord,
)

from ..config import AnalyzeConfig as AnalyzeConfig
from ..types import Timings as Timings
from ..utils import resolve_symbol_for_output as resolve_symbol_for_output
from .outputs import OutputFormatter as OutputFormatter

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
) -> list[Path]: ...
