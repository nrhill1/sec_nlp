from langchain_core.documents import Document as Document

from sec_nlp.core.infra.logger import (
    color_text as color_text,
    logger as logger,
)
from sec_nlp.core.text.keyword import FilterStats as FilterStats

def log_chunk_length_stats(
    *,
    label: str | None,
    symbol: str | None,
    accession: str | None,
    docs: list[Document],
    keyword_field: str | None = None,
    prefix_color: str | None = None,
) -> None: ...
def log_llm_inputs(batch: list[Document], docs: list[Document]) -> None: ...
def log_exhibit_stats(
    *,
    symbol: str,
    chunk_count: int,
    sections_found: int,
    exhibit_docs: int,
    html_files: int,
    accession_count: int | None = None,
    filtered_chunk_count: int | None = None,
    prefilter_skips: dict[str, int] | None = None,
) -> None: ...
def log_document_metadata(
    *,
    symbol: str,
    accession_number: str | None,
    filename: str,
    filing_date: str | None,
    source: str,
    exhibit_number: str | None = None,
) -> None: ...
def log_filter_stats(*, symbol: str | None, stats: FilterStats) -> None: ...
