from typing import TypedDict

from langchain_core.documents import Document as Document

from sec_nlp.types import (
    JsonObject as JsonObject,
    JsonValue as JsonValue,
)

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

def prepare_vector_docs(
    docs: list[Document], *, symbol: str
) -> list[Document]: ...
def build_rollups(
    relevant_results: list[JsonObject],
) -> tuple[list[RollupRecord], set[str], set[str]]: ...
