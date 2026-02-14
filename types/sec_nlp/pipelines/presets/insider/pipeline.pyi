from pathlib import Path
from typing import ClassVar, Literal

from rich.progress import (
    Progress as Progress,
    TaskID as TaskID,
)

from sec_nlp.core.edgar.insider_parser import InsiderParser as InsiderParser
from sec_nlp.pipelines import BasePipeline as BasePipeline

from .config import InsiderSettings as InsiderSettings
from .models import InsiderResult as InsiderResult

class InsiderPipeline(BasePipeline):
    pipeline_type: ClassVar[Literal["insider"]]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    config: InsiderSettings
    @classmethod
    def config_model(cls) -> type[InsiderSettings]: ...
    @classmethod
    def result_model(cls) -> type[InsiderResult]: ...
    def _build_components(self) -> None: ...
    def _get_parser(self) -> InsiderParser: ...
    def run(self) -> InsiderResult: ...
    def _process_symbol(
        self,
        symbol: str,
        *,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> tuple[list[Path], dict[str, int | float | str | None], int, int]: ...
    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        symbol: str,
        phase: str,
        *,
        total: int | None = None,
    ) -> None: ...
