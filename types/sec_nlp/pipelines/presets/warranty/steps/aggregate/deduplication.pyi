from _typeshed import Incomplete

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.types import (
    FilingMetadata as FilingMetadata,
    WarrantyAggregateDict as WarrantyAggregateDict,
    WarrantyExtractionDict as WarrantyExtractionDict,
)
from sec_nlp.types import JsonValue as JsonValue

from ...types import (
    WarrantyMergeBucket as WarrantyMergeBucket,
    WarrantyPeriodRecord as WarrantyPeriodRecord,
)

FieldName: Incomplete

def aggregate_period_records(
    symbol: str,
    filing_meta: FilingMetadata,
    valid_results: list[WarrantyExtractionDict],
) -> list[WarrantyPeriodRecord]: ...
def dedupe_period_records(
    records: list[WarrantyPeriodRecord],
) -> list[WarrantyPeriodRecord]: ...
