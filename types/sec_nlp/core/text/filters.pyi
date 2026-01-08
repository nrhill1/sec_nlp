from enum import StrEnum

from _typeshed import Incomplete
from langchain_core.documents import Document as Document
from pydantic import (
    BaseModel,
    ValidationInfo as ValidationInfo,
)

from sec_nlp.core.infra.logger import logger as logger

class SectionType(StrEnum):
    ITEM = "item"
    EXHIBIT = "exhibit"
    PART = "part"
    CUSTOM = "custom"

class SectionPattern(BaseModel):
    section_type: SectionType
    numbers: list[str]
    custom_pattern: str | None
    require_exact_match: bool
    @classmethod
    def validate_custom_pattern(
        cls, v: str | None, info: ValidationInfo
    ) -> str | None: ...

class SectionFilter:
    QUICK_CHECK_TERMS: dict[SectionType, list[str]]
    WILDCARD_NUMBERS: set[str]
    ANY_NUMBER_PATTERNS: dict[SectionType, str]
    BASE_PATTERNS: dict[SectionType, list[str]]
    SUBSECTION_PATTERNS: dict[SectionType, str]
    patterns: Incomplete
    search_window: Incomplete
    filter_indices: Incomplete
    def __init__(
        self,
        patterns: list[SectionPattern],
        search_window: int = 2000,
        filter_indices: bool = True,
    ) -> None: ...
    def filter_documents(self, docs: list[Document]) -> list[Document]: ...
    def contains_section(self, doc: Document) -> bool: ...
    def extract_section_info(
        self, doc: Document
    ) -> dict[str, list[dict[str, str]] | bool]: ...
    def is_index_document(self, doc: Document) -> bool: ...
    def quick_check_html(
        self, html: str, check_window: int | None = None
    ) -> bool: ...
    def should_process_html(
        self,
        html: str,
        check_window: int | None = None,
        min_content_length: int = 40,
    ) -> tuple[bool, str]: ...
    def batch_prefilter_html(
        self,
        html_list: list[str],
        check_window: int | None = None,
        min_content_length: int = 40,
    ) -> tuple[list[tuple[int, str]], list[tuple[int, str, str]]]: ...

def create_default_section_filter(
    search_window: int = 2000, filter_indices: bool = True
) -> SectionFilter: ...
def create_exhibit_filter(
    exhibit_numbers: list[str],
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter: ...
def create_item_filter(
    item_numbers: list[str],
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter: ...
def create_multi_section_filter(
    patterns: list[SectionPattern],
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter: ...

PROXY_SECTION_PATTERNS: dict[str, str]

def create_proxy_filter(
    sections: list[str] | None = None,
    search_window: int = 3000,
    filter_indices: bool = True,
) -> SectionFilter: ...

HOLDINGS_SECTION_PATTERNS: dict[str, str]

def create_holdings_filter(
    include_cover: bool = False,
    search_window: int = 2000,
    filter_indices: bool = True,
) -> SectionFilter: ...
