from collections.abc import Sequence
from pathlib import Path

from _typeshed import Incomplete
from langchain_core.documents import Document
from unstructured.documents.elements import Element as Element

from sec_nlp.core.infra.logger import (
    color_text as color_text,
    logger as logger,
)
from sec_nlp.core.text.chunking import SentenceSplitter as SentenceSplitter
from sec_nlp.core.text.filters import (
    SectionFilter as SectionFilter,
    create_default_section_filter as create_default_section_filter,
)
from sec_nlp.core.text.keyword import (
    KeywordMatcher as KeywordMatcher,
    KeywordSpec as KeywordSpec,
)
from sec_nlp.core.text.section_extractor import (
    SectionExtractor as SectionExtractor,
)
from sec_nlp.types import JsonDict as JsonDict

class HtmlProcessor:
    chunk_size: Incomplete
    chunk_overlap: Incomplete
    section_chunking: Incomplete
    section_chunk_max_length: Incomplete
    keyword_mode: Incomplete
    def __init__(
        self,
        *,
        chunk_size: int,
        chunk_overlap: int,
        section_chunking: bool,
        section_chunk_max_length: int,
        keyword_mode: str,
    ) -> None: ...
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
