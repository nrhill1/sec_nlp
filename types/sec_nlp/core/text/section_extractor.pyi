from _typeshed import Incomplete
from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.core.text.chunking import SentenceSplitter as SentenceSplitter
from sec_nlp.core.text.filters import (
    SectionFilter as SectionFilter,
    SectionType as SectionType,
)
from sec_nlp.types import JsonValue as JsonValue

class SectionBoundary:
    section_type: Incomplete
    section_number: Incomplete
    start_pos: Incomplete
    end_pos: Incomplete
    title: Incomplete
    def __init__(
        self,
        section_type: str,
        section_number: str,
        start_pos: int,
        end_pos: int | None = None,
        title: str | None = None,
    ) -> None: ...

class ExtractedSection(Document):
    def __init__(
        self,
        page_content: str,
        section_type: str,
        section_number: str,
        start_pos: int,
        end_pos: int | None = None,
        title: str | None = None,
        **metadata: JsonValue,
    ) -> None: ...

class SectionExtractor:
    SECTION_END_PATTERNS: dict[SectionType, list[str]]
    section_filter: Incomplete
    max_section_length: Incomplete
    detect_boundaries: Incomplete
    def __init__(
        self,
        section_filter: SectionFilter,
        max_section_length: int = 500000,
        detect_boundaries: bool = True,
    ) -> None: ...
    def extract_sections(
        self, content: str, metadata: dict[str, JsonValue] | None = None
    ) -> list[ExtractedSection]: ...
    def extract_and_chunk(
        self,
        content: str,
        metadata: dict[str, JsonValue] | None = None,
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
    ) -> list[Document]: ...

def create_section_extractor(
    section_filter: SectionFilter,
    max_section_length: int = 500000,
    detect_boundaries: bool = True,
) -> SectionExtractor: ...
