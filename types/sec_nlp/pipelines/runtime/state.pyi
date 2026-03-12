from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel as BaseModel

from sec_nlp.types import JsonDict as JsonDict

type ProcessingStatus = Literal["success", "partial", "skipped"]

STATE_DIR_NAME: str
STATE_FILE_SUFFIX: str

class ProcessedAccession(BaseModel):
    accession_number: str
    symbol: str
    processed_at: object
    pipeline_type: str
    run_id: UUID
    chunk_count: int
    status: ProcessingStatus

class ProcessingStateMetadata(BaseModel):
    pipeline_type: str
    created_at: object
    updated_at: object
    version: int

class ProcessingStateData(BaseModel):
    metadata: ProcessingStateMetadata
    accessions: dict[str, list[ProcessedAccession]]
    def get_processed_accession_numbers(self, symbol: str) -> set[str]: ...
    def add_accession(self, record: ProcessedAccession) -> None: ...
    def clear_symbol(self, symbol: str) -> int: ...
    def clear_all(self) -> int: ...

class ProcessingState:
    @property
    def state_file(self) -> Path: ...
    @property
    def data(self) -> ProcessingStateData: ...
    def __init__(
        self,
        state_dir: Path,
        pipeline_type: str,
        *,
        auto_save: bool = True,
    ) -> None: ...
    def save(self) -> None: ...
    def is_processed(self, symbol: str, accession: str) -> bool: ...
    def get_pending_accessions(
        self, symbol: str, all_accessions: set[str]
    ) -> set[str]: ...
    def mark_processed(
        self,
        symbol: str,
        accession: str,
        *,
        run_id: UUID,
        chunk_count: int = 0,
        status: ProcessingStatus = "success",
    ) -> None: ...
    def mark_processed_batch(
        self,
        symbol: str,
        accessions: list[str],
        *,
        run_id: UUID,
        chunk_counts: dict[str, int] | None = None,
        status: ProcessingStatus = "success",
    ) -> None: ...
    def clear(self, symbol: str | None = None) -> int: ...
    def get_stats(self) -> JsonDict: ...

def get_state_dir(out_path: Path) -> Path: ...
def load_state(out_path: Path, pipeline_type: str) -> ProcessingState: ...
