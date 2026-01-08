from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

from _typeshed import Incomplete

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.base.result import BaseResult as BaseResult
from sec_nlp.types import (
    JsonDict as JsonDict,
    JsonObject as JsonObject,
)

class PipelineProfiler(AbstractContextManager):
    pipeline_name: Incomplete
    run_id: Incomplete
    output_root: Incomplete
    profile_dir: Incomplete
    profile_path: Incomplete
    tracemalloc_path: Incomplete
    tracemalloc_frames: int
    def __init__(
        self,
        pipeline_name: str,
        run_id: int | str | None = None,
        output_root: Path | None = None,
        tracemalloc_frames: int = 8,
    ) -> None: ...
    def __enter__(self) -> PipelineProfiler: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    def sample_memory(self) -> None: ...
    @property
    def peak_memory_mb(self) -> float | None: ...
    def to_metadata(self) -> JsonObject: ...
    def attach_metadata(
        self, result: BaseResult | None
    ) -> BaseResult | None: ...
