# src/sec_nlp/pipelines/observability/metrics.py
"""Performance metrics collection and reporting for pipelines."""

import time
from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.output_io import write_json
from sec_nlp.pipelines.types import CustomMetricDict, MetricsSummary
from sec_nlp.types import JsonDict


@dataclass
class MetricPoint:
    """Single metric measurement."""

    name: str
    value: float
    unit: str
    timestamp: float | None = field(default_factory=time.time)
    tags: dict[str, str] | None = field(default_factory=dict)


@dataclass
class TimerMetric:
    """Timer metric with start/end tracking."""

    name: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Get duration in seconds."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    def stop(self) -> float:
        """Stop timer and return duration."""
        if self.end_time is None:
            self.end_time = time.time()
        return self.duration


class PipelineMetrics:
    """Collects and aggregates pipeline performance metrics."""

    def __init__(self, pipeline_name: str):
        """Initialize metrics collector.

        Args:
            pipeline_name: Name of the pipeline being measured
        """
        self.pipeline_name = pipeline_name
        self.start_time = time.time()
        self.end_time: float | None = None

        # Metric storage
        self.counters: dict[str, int] = defaultdict(int)
        self.gauges: dict[str, float] = {}
        self.timers: dict[str, list[float]] = defaultdict(list)
        self.active_timers: dict[str, TimerMetric] = {}
        self.custom_metrics: list[MetricPoint] = []

        # Memory tracking
        self.memory_samples: list[tuple[float, float]] = []
        self._track_memory = False

    def start(self) -> None:
        """Start metrics collection."""
        self.start_time = time.time()
        logger.debug("Started metrics collection for %s", self.pipeline_name)

    def stop(self) -> None:
        """Stop metrics collection."""
        self.end_time = time.time()
        logger.debug("Stopped metrics collection for %s", self.pipeline_name)

    @property
    def total_duration(self) -> float:
        """Get total pipeline duration in seconds."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    def increment(
        self, counter: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None:
        """Increment a counter metric.

        Args:
            counter: Counter name
            value: Value to increment by
            tags: Optional tags for the metric
        """
        key = self._make_key(counter, tags)
        self.counters[key] += value

    def set_gauge(
        self, gauge: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Set a gauge metric.

        Args:
            gauge: Gauge name
            value: Current value
            tags: Optional tags for the metric
        """
        key = self._make_key(gauge, tags)
        self.gauges[key] = value

    def record_time(
        self, timer: str, duration: float, tags: dict[str, str] | None = None
    ) -> None:
        """Record a timing measurement.

        Args:
            timer: Timer name
            duration: Duration in seconds
            tags: Optional tags for the metric
        """
        key = self._make_key(timer, tags)
        self.timers[key].append(duration)

    @contextmanager
    def timer(
        self, name: str, tags: dict[str, str] | None = None
    ) -> Generator[None]:
        """Context manager for timing operations.

        Example:
            with metrics.timer("download_filing", tags={"symbol": "AAPL"}):
                download_filing()
        """
        key = self._make_key(name, tags)
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.timers[key].append(duration)

    def record_custom(
        self,
        name: str,
        value: float,
        unit: str,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a custom metric.

        Args:
            name: Metric name
            value: Metric value
            unit: Unit of measurement
            tags: Optional tags for the metric
        """
        self.custom_metrics.append(
            MetricPoint(
                name,
                value,
                unit,
                tags=tags or {},
            )
        )

    def sample_memory(self) -> None:
        """Sample current memory usage."""
        try:
            import os

            import psutil

            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / (1024 * 1024)
            self.memory_samples.append((time.time(), memory_mb))
        except ImportError:
            if not self._track_memory:
                logger.debug("psutil not installed, memory tracking disabled")
                self._track_memory = True

    def _make_key(self, name: str, tags: dict[str, str] | None) -> str:
        """Create metric key from name and tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"

    def get_summary(self) -> MetricsSummary:
        """Get summary of all collected metrics.

        Returns:
            Dictionary with metric summaries
        """
        from sec_nlp.pipelines.types import TimerStats

        timers_summary: dict[str, TimerStats] = {}
        summary: MetricsSummary = {
            "pipeline": self.pipeline_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_seconds": self.total_duration,
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "timers": timers_summary,
            "memory": {},
            "custom_metrics": [],
        }

        # Aggregate timer statistics
        for name, durations in self.timers.items():
            if durations:
                timers_summary[name] = TimerStats(
                    count=len(durations),
                    total=sum(durations),
                    mean=sum(durations) / len(durations),
                    min_value=min(durations),
                    max_value=max(durations),
                    p50=self._percentile(durations, 50),
                    p95=self._percentile(durations, 95),
                    p99=self._percentile(durations, 99),
                )

        # Memory statistics
        from sec_nlp.pipelines.types import MemoryStats

        if self.memory_samples:
            memory_values = [mb for _, mb in self.memory_samples]
            summary["memory"] = MemoryStats(
                samples=len(self.memory_samples),
                mean_mb=sum(memory_values) / len(memory_values),
                max_mb=max(memory_values),
                min_mb=min(memory_values),
            )

        # Custom metrics
        if self.custom_metrics:
            summary["custom_metrics"] = [
                CustomMetricDict(
                    name=m.name,
                    value=m.value,
                    unit=m.unit,
                    tags=m.tags,
                )
                for m in self.custom_metrics
            ]

        return summary

    def print_report(self) -> None:
        """Print formatted metrics report."""
        summary = self.get_summary()

        logger.info("=" * 70)
        logger.info(f"Performance Metrics: {self.pipeline_name}")
        logger.info("=" * 70)
        logger.info(f"Total Duration: {self.total_duration:.2f}s")
        logger.info("")

        # Counters
        if summary["counters"]:
            logger.info("Counters:")
            for name, value in sorted(summary["counters"].items()):
                logger.info(f"  {name}: {value:,}")
            logger.info("")

        # Gauges
        if summary["gauges"]:
            logger.info("Gauges:")
            for name, gauge_val in sorted(summary["gauges"].items()):
                logger.info(f"  {name}: {gauge_val:.2f}")
            logger.info("")

        # Timers
        if summary["timers"]:
            logger.info("Timers:")
            for name, stats in sorted(summary["timers"].items()):
                logger.info(f"  {name}:")
                logger.info(f"    Count: {stats['count']}")
                logger.info(f"    Total: {stats['total']:.3f}s")
                logger.info(f"    Mean: {stats['mean']:.3f}s")
                logger.info(f"    Min: {stats['min_value']:.3f}s")
                logger.info(f"    Max: {stats['max_value']:.3f}s")
                logger.info(f"    P95: {stats['p95']:.3f}s")
            logger.info("")

        # Memory
        if summary["memory"]:
            logger.info("Memory:")
            mem = summary["memory"]
            logger.info(f"  Mean: {mem['mean_mb']:.2f} MB")
            logger.info(f"  Peak: {mem['max_mb']:.2f} MB")
            logger.info(f"  Samples: {mem['samples']}")
            logger.info("")

        logger.info("=" * 70)

    def export_json(self, output_path: Path) -> None:
        """Export metrics to JSON file.

        Args:
            output_path: Path to output JSON file
        """
        summary = self.get_summary()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        write_json(output_path, self._serialize_summary(summary))

        logger.info("Metrics exported to %s", output_path)

    @staticmethod
    def _serialize_summary(summary: MetricsSummary) -> JsonDict:
        """Convert metrics summary to JSON-safe dictionary."""
        timers: JsonDict = {}
        for name, stats in summary["timers"].items():
            timers[name] = {
                "count": stats["count"],
                "total": stats["total"],
                "mean": stats["mean"],
                "min_value": stats["min_value"],
                "max_value": stats["max_value"],
                "p50": stats["p50"],
                "p95": stats["p95"],
                "p99": stats["p99"],
            }

        memory: JsonDict = {}
        mem = summary["memory"]
        if mem:
            memory = {
                "samples": mem["samples"],
                "mean_mb": mem["mean_mb"],
                "max_mb": mem["max_mb"],
                "min_mb": mem["min_mb"],
            }

        custom_metrics: list[JsonDict] = []
        for metric in summary["custom_metrics"]:
            custom_metrics.append(
                {
                    "name": metric["name"],
                    "value": metric["value"],
                    "unit": metric["unit"],
                    "tags": metric.get("tags"),
                }
            )

        return {
            "pipeline": summary["pipeline"],
            "start_time": summary["start_time"],
            "end_time": summary["end_time"],
            "total_duration_seconds": summary["total_duration_seconds"],
            "counters": dict(summary["counters"]),
            "gauges": dict(summary["gauges"]),
            "timers": timers,
            "memory": memory,
            "custom_metrics": custom_metrics,
        }

    def export_csv(self, output_path: Path) -> None:
        """Export timer metrics to CSV file.

        Args:
            output_path: Path to output CSV file
        """
        import csv

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "metric_name",
                    "count",
                    "total_s",
                    "mean_s",
                    "min_s",
                    "max_s",
                    "p50_s",
                    "p95_s",
                    "p99_s",
                ]
            )

            summary = self.get_summary()
            for name, stats in sorted(summary["timers"].items()):
                writer.writerow(
                    [
                        name,
                        stats["count"],
                        f"{stats['total']:.3f}",
                        f"{stats['mean']:.3f}",
                        f"{stats['min_value']:.3f}",
                        f"{stats['max_value']:.3f}",
                        f"{stats['p50']:.3f}",
                        f"{stats['p95']:.3f}",
                        f"{stats['p99']:.3f}",
                    ]
                )

        logger.info("Metrics exported to %s", output_path)

    @staticmethod
    def _percentile(values: list[float], percentile: int) -> float:
        """Calculate percentile of values.

        Args:
            values: List of values
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value
        """
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]


@contextmanager
def track_pipeline_metrics(
    pipeline_name: str, auto_report: bool = True
) -> Generator[PipelineMetrics]:
    """Context manager for tracking pipeline metrics.

    Example:
        with track_pipeline_metrics("my_pipeline") as metrics:
            # Run pipeline
            metrics.increment("documents_processed")
            with metrics.timer("llm_inference"):
                process_with_llm()

    Args:
        pipeline_name: Name of the pipeline
        auto_report: Whether to print report when done

    Yields:
        PipelineMetrics instance
    """
    metrics = PipelineMetrics(pipeline_name)
    metrics.start()
    try:
        yield metrics
    finally:
        metrics.stop()
        if auto_report:
            metrics.print_report()
