from collections.abc import Iterable, Mapping, Sequence
from typing import TypedDict

from langchain_core.documents import Document as Document
from qdrant_client.models import Filter as Filter

from sec_nlp.pipelines.types import (
    AnalysisResultDict as AnalysisResultDict,
    MetadataMap as MetadataMap,
    MetadataValue as MetadataValue,
)
from sec_nlp.types import (
    JsonDict as JsonDict,
    JsonObject as JsonObject,
    JsonValue as JsonValue,
)

type MetadataFilterValue = str | int | bool
type MetadataFilterInput = MetadataFilterValue | Sequence[MetadataFilterValue]
type MetadataFilters = Mapping[str, MetadataFilterInput]

class RollupWorkItem(TypedDict):
    accession_number: str
    filing_date: str | None
    form_type: str | None
    exhibit_number: str | None
    filename: str | None
    chunk_count: int
    parties: set[str]
    suppliers: set[str]
    key_terms: set[str]
    obligations: set[str]
    summaries: list[str]

class RollupRecord(TypedDict):
    accession_number: str
    filing_date: str | None
    form_type: str | None
    exhibit_number: str | None
    filename: str | None
    chunk_count: int
    parties: list[str]
    suppliers: list[str]
    key_terms: list[str]
    obligations: list[str]
    summaries: list[str]

def get_accession_from_metadata(metadata: MetadataMap | None) -> str: ...
def group_results_by_accession(
    results: list[AnalysisResultDict], fallback_meta: MetadataMap | None
) -> dict[str, list[AnalysisResultDict]]: ...
def build_metadata_filter(raw_filters: MetadataFilters) -> Filter | None: ...
def coerce_meta_str(value: MetadataValue) -> str | None: ...
def get_meta_str(meta: MetadataMap, key: str) -> str | None: ...
def get_meta_str_any(
    meta: MetadataMap,
    keys: Iterable[str],
    *,
    include_source_meta: bool = True,
) -> str | None: ...
def normalize_metadata_for_output(metadata: MetadataMap | None) -> JsonDict: ...
def prepare_vector_docs(
    docs: list[Document], *, symbol: str
) -> list[Document]: ...
def build_rollups(
    relevant_results: list[JsonObject],
) -> tuple[list[RollupRecord], set[str], set[str]]: ...
