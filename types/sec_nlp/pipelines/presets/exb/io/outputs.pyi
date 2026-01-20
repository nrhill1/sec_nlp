from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from langchain_core.documents import Document as Document

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.output_io import (
    build_run_file_stem as build_run_file_stem,
    write_json as write_json,
    write_yaml as write_yaml,
)
from sec_nlp.types import (
    JsonDict as JsonDict,
    JsonObject as JsonObject,
    JsonValue as JsonValue,
)

from ..config import ExhibitConfig as ExhibitConfig

class AccessionRecord(TypedDict):
    accession_number: str
    form_type: str | None
    filing_date: str | None
    chunk_count: int
    exhibit_numbers: list[str]
    exhibit_categories: list[JsonValue]
    filenames: list[str]
    sources: list[str]
    descriptions: list[str]
    keyword_hits: list[str]

@dataclass
class AccessionAccumulator:
    accession_number: str
    form_type: str | None
    filing_date: str | None
    chunk_count: int = ...
    exhibit_numbers: set[str] = field(default_factory=set)
    exhibit_categories: set[JsonValue] = field(default_factory=set)
    filenames: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    descriptions: set[str] = field(default_factory=set)
    keyword_hits: set[str] = field(default_factory=set)

def write_exhibit_outputs(
    *, symbol: str, docs: list[Document], config: ExhibitConfig
) -> list[Path]: ...
def write_indexing_manifest(
    *, symbol: str, docs: list[Document], config: ExhibitConfig
) -> Path | None: ...
