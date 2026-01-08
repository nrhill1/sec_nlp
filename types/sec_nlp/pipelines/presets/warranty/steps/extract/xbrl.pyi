from pathlib import Path
from typing import TypedDict

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.types import (
    SourceMetadata as SourceMetadata,
    WarrantyExtractionDict as WarrantyExtractionDict,
)

WARRANTY_XBRL_TAGS: list[str]

class XbrlValueEntry(TypedDict):
    value: float
    tag: str
    context_ref: str | None
    period_end: str | None

type XbrlValueSets = dict[str, list[XbrlValueEntry]]

class XbrlYearBucket(TypedDict, total=False):
    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None
    period: str | int | None
    period_end: str | None
    accession_number: str | None
    confidence: float
    source_metadata: SourceMetadata

def load_xbrl_for_filing(
    symbol: str, filing_dir: Path, accession_number: str
) -> list[Document]: ...
def extract_from_xbrl_docs(
    symbol: str, docs: list[Document]
) -> list[WarrantyExtractionDict]: ...
