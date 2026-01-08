from pathlib import Path
from typing import Literal

from _typeshed import Incomplete

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.output_io import (
    build_accession_dir as build_accession_dir,
    write_json as write_json,
    write_yaml as write_yaml,
)
from sec_nlp.pipelines.types import (
    AnalysisResultDict as AnalysisResultDict,
    MetadataMap as MetadataMap,
)

from ..models import (
    Aggregates as Aggregates,
    AnalysisDiagnostics as AnalysisDiagnostics,
    AnalysisOutput as AnalysisOutput,
    ExecutiveSummary as ExecutiveSummary,
    FilingInfo as FilingInfo,
)

class OutputFormatter:
    export_format: Incomplete
    confidence_threshold: Incomplete
    topics: Incomplete
    include_raw_chunks: Incomplete
    def __init__(
        self,
        export_format: Literal["json", "csv", "yaml", "both", "yaml_csv"],
        confidence_threshold: float,
        topics: list[str] | None = None,
        include_raw_chunks: bool = False,
    ) -> None: ...
    def is_relevant_result(self, result: AnalysisResultDict) -> bool: ...
    def build_output(
        self,
        symbol: str,
        filing_meta: MetadataMap,
        analysis_results: list[AnalysisResultDict],
        relevant_results: list[AnalysisResultDict],
        search_queries: list[str] | None = None,
        timings: dict[str, float] | None = None,
    ) -> AnalysisOutput: ...
    def export(
        self, output: AnalysisOutput, output_dir: Path, accession: str
    ) -> list[Path]: ...
