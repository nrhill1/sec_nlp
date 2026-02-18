from pathlib import Path
from typing import ClassVar, Literal

from rich.progress import (
    Progress as Progress,
    TaskID as TaskID,
)

from sec_nlp.core.edgar.xbrl_facts import XbrlParser as XbrlParser
from sec_nlp.pipelines import BasePipeline as BasePipeline

from .config import FinancialsSettings as FinancialsSettings
from .models import FinancialsResult as FinancialsResult

class FinancialsPipeline(BasePipeline):
    pipeline_type: ClassVar[Literal["financials"]]
    description: ClassVar[str]
    requires_llm: ClassVar[bool]
    config: FinancialsSettings
    @classmethod
    def config_model(cls) -> type[FinancialsSettings]: ...
    @classmethod
    def result_model(cls) -> type[FinancialsResult]: ...
    def _build_components(self) -> None: ...
    def _get_parser(self) -> XbrlParser: ...
    def run(self) -> FinancialsResult: ...
    def _process_symbol(
        self,
        symbol: str,
        *,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> tuple[list[Path], dict[str, int | str], int]: ...
    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        symbol: str,
        phase: str,
        *,
        total: int | None = None,
    ) -> None: ...
