import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from _typeshed import Incomplete

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.output_io import write_json as write_json
from sec_nlp.pipelines.types import (
    CustomMetricDict as CustomMetricDict,
    MetricsSummary as MetricsSummary,
)
from sec_nlp.types import JsonDict as JsonDict

@dataclass
class MetricPoint:
    name: str
    value: float
    unit: str
    timestamp: float | None = field(default_factory=time.time)
    tags: dict[str, str] | None = field(default_factory=dict)

@dataclass
class TimerMetric:
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = ...
    tags: dict[str, str] = field(default_factory=dict)
    @property
    def duration(self) -> float: ...
    def stop(self) -> float: ...

class PipelineMetrics:
    pipeline_name: Incomplete
    start_time: Incomplete
    end_time: float | None
    counters: dict[str, int]
    gauges: dict[str, float]
    timers: dict[str, list[float]]
    active_timers: dict[str, TimerMetric]
    custom_metrics: list[MetricPoint]
    memory_samples: list[tuple[float, float]]
    def __init__(self, pipeline_name: str) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    @property
    def total_duration(self) -> float: ...
    def increment(
        self, counter: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None: ...
    def set_gauge(
        self, gauge: str, value: float, tags: dict[str, str] | None = None
    ) -> None: ...
    def record_time(
        self, timer: str, duration: float, tags: dict[str, str] | None = None
    ) -> None: ...
    @contextmanager
    def timer(
        self, name: str, tags: dict[str, str] | None = None
    ) -> Generator[None]: ...
    def record_custom(
        self,
        name: str,
        value: float,
        unit: str,
        tags: dict[str, str] | None = None,
    ) -> None: ...
    def sample_memory(self) -> None: ...
    def get_summary(self) -> MetricsSummary: ...
    def print_report(self) -> None: ...
    def export_json(self, output_path: Path) -> None: ...
    def export_csv(self, output_path: Path) -> None: ...

@contextmanager
def track_pipeline_metrics(
    pipeline_name: str, auto_report: bool = True
) -> Generator[PipelineMetrics]: ...
