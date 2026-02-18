from typing import ClassVar, Literal

from sec_nlp.pipelines.base.config import (
    BasePipelineSettings as BasePipelineSettings,
)

class FinancialsSettings(BasePipelineSettings):
    pipeline_type: ClassVar[Literal["financials"]]
    form_types: list[str]
    periods: int
    compute_ratios: bool
    output_format: Literal["csv", "json", "yaml", "all"]
    include_delta_report: bool
    @classmethod
    def normalize_form_types(
        cls, value: list[str] | str | None
    ) -> list[str]: ...
    def pipeline_label(self) -> str: ...
