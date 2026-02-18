from pathlib import Path
from typing import ClassVar, Literal

from rich.progress import (
    Progress as Progress,
    TaskID as TaskID,
)

from sec_nlp.core.edgar.holdings_parser import HoldingsParser as HoldingsParser
from sec_nlp.pipelines import BasePipeline as BasePipeline

from .config import HoldingsSettings as HoldingsSettings
from .models import HoldingsResult as HoldingsResult

class HoldingsPipeline(BasePipeline):
    pipeline_type: ClassVar[Literal["holdings"]]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    config: HoldingsSettings
    @classmethod
    def config_model(cls) -> type[HoldingsSettings]: ...
    @classmethod
    def result_model(cls) -> type[HoldingsResult]: ...
    def _build_components(self) -> None: ...
    def _get_parser(self) -> HoldingsParser: ...
    def run(self) -> HoldingsResult: ...
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
