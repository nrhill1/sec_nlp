from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from _typeshed import Incomplete

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.core.infra.settings import PROJECT_ROOT as PROJECT_ROOT
from sec_nlp.pipelines.types import QueryParam as QueryParam

class RunRecordDict(TypedDict):
    record_id: int
    short_id: str
    run_id: str
    pipeline_type: str
    started_at: str | None
    completed_at: str | None
    status: str
    output_dir: str | None
    duration_seconds: float | None

DEFAULT_REGISTRY_PATH: Path

@dataclass(frozen=True)
class RunRecord:
    record_id: int
    run_id: str
    pipeline_type: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    output_dir: str | None
    metadata: str | None
    @property
    def short_id(self) -> str: ...
    @property
    def duration_seconds(self) -> float | None: ...
    def to_dict(self) -> RunRecordDict: ...

class RunRegistry:
    db_path: Incomplete
    def __init__(self, db_path: Path | None = None) -> None: ...
    def register_run(
        self,
        run_id: str,
        pipeline_type: str,
        started_at: datetime | None = None,
        output_dir: str | None = None,
    ) -> int | None: ...
    def complete_run(
        self, run_id: str, success: bool = True, metadata: str | None = None
    ) -> None: ...
    def get_run(self, identifier: int | str) -> RunRecord | None: ...
    def list_runs(
        self,
        pipeline_type: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[RunRecord]: ...
    def delete_run(self, identifier: int | str) -> bool: ...
    def prune_runs(
        self,
        older_than_days: int | None = None,
        keep_last: int | None = None,
        pipeline_type: str | None = None,
    ) -> int: ...
    def get_stats(self) -> dict[str, int | dict[str, int] | str]: ...

def get_registry() -> RunRegistry: ...
