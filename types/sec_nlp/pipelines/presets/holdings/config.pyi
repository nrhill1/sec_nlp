from typing import ClassVar, Literal

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.pipelines.base.config import (
    BasePipelineSettings as BasePipelineSettings,
)

class HoldingsSettings(BasePipelineSettings):
    pipeline_type: ClassVar[Literal["holdings"]]
    mode: FilingMode
    forms: list[str] | None
    quarters: int
    top_holders: int
    cusip: str | None
    filer_ciks: list[str]
    output_format: Literal["csv", "json", "yaml", "all"]
    @classmethod
    def validate_mode(cls, value: FilingMode) -> FilingMode: ...
    @classmethod
    def validate_forms(
        cls, value: list[str] | str | None
    ) -> list[str] | None: ...
    @classmethod
    def normalize_cusip(cls, value: str | None) -> str | None: ...
    def pipeline_label(self) -> str: ...
