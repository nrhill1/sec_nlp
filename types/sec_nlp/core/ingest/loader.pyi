from collections.abc import Generator, Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Literal, Protocol, TypedDict

from _typeshed import Incomplete
from langchain_core.documents import Document as Document
from pydantic import BaseModel
from unstructured.documents.elements import Element as Element

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.core.infra.logger import (
    format_size as format_size,
    logger as logger,
)
from sec_nlp.core.ingest import filings as filings
from sec_nlp.core.ingest.downloader import download_filings as download_filings
from sec_nlp.core.ingest.parser import HtmlProcessor as HtmlProcessor
from sec_nlp.core.ingest.types import DownloadResults as DownloadResults
from sec_nlp.core.text.filters import SectionFilter as SectionFilter
from sec_nlp.core.text.section_extractor import (
    SectionExtractor as SectionExtractor,
)
from sec_nlp.types import JsonDict as JsonDict

class LoaderRunMetadata(TypedDict):
    work_folder: str
    download_results: DownloadResults
    per_symbol_doc_counts: dict[str, int]
    total_documents: int

class FilingRecord(Protocol):
    acceptance_date: str

class Loader(BaseModel):
    model_config: Incomplete
    email: str
    downloads_folder: Path
    company_name: str
    fetch_mode: Literal["download"]
    chunk_size: int
    chunk_overlap: int
    section_chunking: bool
    section_chunk_max_length: int
    keywords: list[str] | None
    keyword_mode: Literal["any", "all"]
    keyword_boundary: bool
    section_filter: SectionFilter | None
    use_async: bool
    max_workers: int
    def model_post_init(self, /, __ctx: None) -> None: ...
    def add_symbol(self, symbol: str) -> None: ...
    def add_symbols(self, symbols: Iterable[str]) -> None: ...
    def load_documents(
        self,
        mode: FilingMode = ...,
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_symbol: int | None = None,
        perform_download: bool = True,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> list[Document]: ...
    def load_texts(
        self,
        mode: FilingMode = ...,
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_symbol: int | None = None,
        perform_download: bool = True,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> list[str]: ...
    def html_paths_for_symbol(
        self,
        symbol: str,
        mode: FilingMode,
        base: Path,
        limit: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Path]: ...
    def transform_html(
        self,
        html_path: Path,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]: ...
    def transform_html_string(
        self,
        html: str,
        metadata: dict[str, str | int | float] | None = None,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]: ...
    async def transform_html_async(
        self,
        html_path: Path,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]: ...
    def batch_transform_html(
        self,
        html_paths: list[Path],
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
        concurrent: bool = True,
    ) -> list[Document]: ...
    def load_documents_stream(
        self,
        mode: FilingMode = ...,
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_symbol: int | None = None,
        perform_download: bool = True,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Generator[Document, None, LoaderRunMetadata]: ...
    def load_texts_stream(
        self,
        mode: FilingMode = ...,
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_symbol: int | None = None,
        perform_download: bool = True,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Generator[str, None, LoaderRunMetadata]: ...
    @property
    def last_meta(self) -> LoaderRunMetadata: ...
    def load_xbrl_facts(
        self,
        tags: list[str],
        mode: FilingMode,
        limit_per_symbol: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Document]: ...
