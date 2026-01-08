from enum import StrEnum

from _typeshed import Incomplete
from langchain_core.documents import Document as Document
from pydantic import BaseModel

from sec_nlp.types import JsonObject as JsonObject

class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"

class TextChange:
    change_type: ChangeType
    old_text: str | None
    new_text: str | None
    similarity: float
    context: str | None

class FilingDiff(BaseModel):
    model_config: Incomplete
    symbol: str
    old_period: str
    new_period: str
    old_filing_date: str | None
    new_filing_date: str | None
    form_type: str
    total_sections_compared: int
    sections_added: int
    sections_removed: int
    sections_modified: int
    sections_unchanged: int
    overall_similarity: float
    changes: list[JsonObject]
    material_changes: list[JsonObject]

class CompanyComparison(BaseModel):
    model_config: Incomplete
    symbols: list[str]
    period: str
    form_type: str
    company_summaries: dict[str, JsonObject]
    comparisons: list[JsonObject]
    common_themes: list[str]
    unique_items: dict[str, list[str]]

def compute_text_similarity(text1: str, text2: str) -> float: ...
def get_text_diff(
    old_text: str, new_text: str, context_lines: int = 3
) -> list[str]: ...
def extract_changes(
    old_text: str, new_text: str, min_change_length: int = 50
) -> list[TextChange]: ...
def compare_documents(
    old_docs: list[Document],
    new_docs: list[Document],
    section_key: str = "section",
) -> dict[str, list[TextChange]]: ...
def identify_material_changes(
    changes: list[TextChange],
    keywords: list[str] | None = None,
    min_similarity_diff: float = 0.3,
) -> list[TextChange]: ...
