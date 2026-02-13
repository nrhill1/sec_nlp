from typing import ClassVar, Literal

from sec_nlp.core.edgar.filing_mode import FilingMode as FilingMode
from sec_nlp.pipelines.base.config import (
    BasePipelineSettings as BasePipelineSettings,
)

class InsiderSettings(BasePipelineSettings):
    pipeline_type: ClassVar[Literal["insider"]]
    mode: FilingMode
    forms: list[str] | None
    lookback_months: int
    alert_cluster_threshold: int
    alert_window_days: int
    large_trade_threshold_shares: float
    output_format: Literal["csv", "json", "yaml", "all"]
    @classmethod
    def validate_mode(cls, value: FilingMode) -> FilingMode: ...
    @classmethod
    def validate_forms(
        cls, value: list[str] | str | None
    ) -> list[str] | None: ...
    @classmethod
    def parse_lookback_months(cls, value: int | str) -> int: ...
    def pipeline_label(self) -> str: ...
