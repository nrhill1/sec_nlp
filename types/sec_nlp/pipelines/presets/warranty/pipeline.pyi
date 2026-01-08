from typing import ClassVar, Literal

from sec_nlp.core.infra.logger import (
    log_divider as log_divider,
    logger as logger,
)
from sec_nlp.core.ingest.loader import Loader as Loader
from sec_nlp.core.text.filters import (
    SectionFilter as SectionFilter,
    create_item_filter as create_item_filter,
)
from sec_nlp.pipelines import BasePipeline as BasePipeline
from sec_nlp.pipelines.observability.telemetry import (
    log_chunk_length_stats as log_chunk_length_stats,
)
from sec_nlp.pipelines.output_io import (
    build_accession_file_stem as build_accession_file_stem,
    build_run_file_stem as build_run_file_stem,
    write_json as write_json,
)
from sec_nlp.pipelines.types import (
    FilingMetadata as FilingMetadata,
    WarrantyExtractionDict as WarrantyExtractionDict,
)
from sec_nlp.types import ResultDict as ResultDict

from .config import WarrantyConfig as WarrantyConfig
from .io.payloads import (
    WarrantyOutputPayload as WarrantyOutputPayload,
    WarrantyPeriodPayload as WarrantyPeriodPayload,
    WarrantyProcessingPayload as WarrantyProcessingPayload,
    WarrantySummaryPayload as WarrantySummaryPayload,
)
from .models import WarrantyResult as WarrantyResult
from .steps.aggregate.deduplication import (
    aggregate_period_records as aggregate_period_records,
    dedupe_period_records as dedupe_period_records,
)
from .steps.extract.xbrl import (
    extract_from_xbrl_docs as extract_from_xbrl_docs,
    load_xbrl_for_filing as load_xbrl_for_filing,
)
from .types import WarrantyPeriodRecord as WarrantyPeriodRecord

class WarrantyPipeline(BasePipeline):
    pipeline_type: ClassVar[Literal["warranty"]]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    config: WarrantyConfig
    @classmethod
    def config_model(cls) -> type[WarrantyConfig]: ...
    @classmethod
    def result_model(cls) -> type[WarrantyResult]: ...
    def run(self) -> WarrantyResult: ...
