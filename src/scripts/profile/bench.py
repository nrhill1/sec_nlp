# src/scripts/profile/bench.py
"""Microbenchmarks for performance-sensitive routines."""

from __future__ import annotations

import random
import string
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev
from time import perf_counter
from typing import Literal

# Add src to path before other imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import setup_import_path  # noqa: E402

# Setup import path securely
setup_import_path()

from pydantic import Field  # noqa: E402
from pydantic_settings import (  # noqa: E402
    BaseSettings,
    CliApp,
    SettingsConfigDict,
)

from sec_nlp.core.infra.logger import logger, setup_logging  # noqa: E402
from sec_nlp.core.text.deduplication import (  # noqa: E402
    SimHashConfig,
    SimHashDeduplicator,
)
from sec_nlp.core.text.keyword import KeywordMatcher, KeywordSpec  # noqa: E402
from sec_nlp.pipelines.base.validation import ValidationResult  # noqa: E402
from sec_nlp.pipelines.presets.analyze.models import (  # noqa: E402
    Aggregates,
    AnalysisDiagnostics,
    AnalysisOutput,
    ExecutiveSummary,
    FilingInfo,
)


@dataclass(frozen=True)
class BenchmarkCase:
    """Single benchmark scenario and its executable workload."""

    name: str
    description: str
    run: Callable[[int], None]


@dataclass(frozen=True)
class BenchmarkStats:
    """Aggregate timing and memory metrics for a benchmark case."""

    name: str
    iterations: int
    repeats: int
    mean_s: float
    min_s: float
    max_s: float
    stdev_s: float

    @property
    def mean_per_op_us(self) -> float:
        return (self.mean_s / self.iterations) * 1_000_000

    @property
    def min_per_op_us(self) -> float:
        return (self.min_s / self.iterations) * 1_000_000

    @property
    def max_per_op_us(self) -> float:
        return (self.max_s / self.iterations) * 1_000_000

    @property
    def ops_per_sec(self) -> float:
        if self.mean_s <= 0:
            return 0.0
        return self.iterations / self.mean_s


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format headers and rows as an aligned text table."""
    if not rows:
        return ""
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _format_row(values: Iterable[str]) -> str:
        """Format one table row using precomputed column widths."""
        parts = []
        for idx, value in enumerate(values):
            if idx == 0:
                parts.append(value.ljust(widths[idx]))
            else:
                parts.append(value.rjust(widths[idx]))
        return "  ".join(parts)

    lines = [_format_row(headers), _format_row(["-" * w for w in widths])]
    lines.extend(_format_row(row) for row in rows)
    return "\n".join(lines)


def _run_case(
    case: BenchmarkCase,
    iterations: int,
    repeats: int,
    warmup: int,
) -> BenchmarkStats:
    """Execute one benchmark case and collect timing statistics."""
    for _ in range(warmup):
        case.run(iterations)

    durations: list[float] = []
    for _ in range(repeats):
        start = perf_counter()
        case.run(iterations)
        durations.append(perf_counter() - start)

    mean_s = mean(durations)
    stdev_s = stdev(durations) if len(durations) > 1 else 0.0
    return BenchmarkStats(
        name=case.name,
        iterations=iterations,
        repeats=repeats,
        mean_s=mean_s,
        min_s=min(durations),
        max_s=max(durations),
        stdev_s=stdev_s,
    )


def _random_texts(count: int, length: int, rng: random.Random) -> list[str]:
    """Generate deterministic random text samples for benchmarks."""
    alphabet = string.ascii_letters + string.digits + " "
    return [
        "".join(rng.choice(alphabet) for _ in range(length))
        for _ in range(count)
    ]


def _build_cases(config: BenchmarkConfig) -> list[BenchmarkCase]:
    """Build cases."""
    rng = random.Random(config.seed)
    texts = _random_texts(config.iterations, config.text_size, rng)

    def _run_simhash(iterations: int) -> None:
        """Run SimHash dedupe microbenchmark for configured iterations."""
        deduper = SimHashDeduplicator(
            config=SimHashConfig(
                num_bits=config.simhash_bits,
                max_distance=config.simhash_max_distance,
            )
        )
        for text in texts[:iterations]:
            deduper.add_if_unique(text)

    def _run_keyword_score(iterations: int) -> None:
        """Run keyword-scoring microbenchmark for configured iterations."""
        specs = [
            KeywordSpec("warranty", 2, 1.5),
            KeywordSpec("recall", 2, 1.2),
            KeywordSpec("liability", 1, 1.0),
            KeywordSpec("risk", 1, 0.8),
            KeywordSpec("defect", 1, 0.7),
        ]
        text = "warranty liability and recall risk " * 20
        for _ in range(iterations):
            KeywordMatcher.score_keywords(text, specs)

    def _run_validation_result(iterations: int) -> None:
        """Run validation-model construction benchmark iterations."""
        for i in range(iterations):
            ValidationResult(
                passed=True,
                check_name="benchmark",
                message="ok",
                severity="info",
                details={"idx": i},
            )

    def _run_analysis_output(iterations: int) -> None:
        """Run analysis-output model construction benchmark iterations."""
        for _i in range(iterations):
            AnalysisOutput(
                symbol="AAPL",
                filing=FilingInfo(
                    accession_number="0000000000",
                    form_type="10-K",
                    acceptance_date="2024-01-01",
                    filing_date="2024-01-02",
                ),
                executive_summary=ExecutiveSummary(
                    status="ok",
                    total_chunks=10,
                    relevant_count=2,
                    average_confidence=0.82,
                    top_tags=["warranty"],
                    top_topics=["recall"],
                    key_points=["Point A", "Point B"],
                ),
                aggregates=Aggregates(
                    tag_frequency={"warranty": 2},
                    sentiment_breakdown={"neutral": 2},
                    sections_covered={"1A": 1},
                    topic_hits_frequency={"recall": 2},
                    forward_looking_count=0,
                ),
                diagnostics=AnalysisDiagnostics(
                    chunks_analyzed=10,
                    chunks_successful=10,
                    chunks_failed=0,
                    chunks_relevant=2,
                    success_rate=1.0,
                    relevant_rate=0.2,
                    timings={"analyze": 0.25},
                    confidence_threshold=0.5,
                ),
                results=[
                    {
                        "is_relevant": True,
                        "confidence_score": 0.9,
                        "summary": "Sample summary",
                        "key_points": ["Key point"],
                        "tags": ["warranty"],
                        "source_metadata": {"symbol": "AAPL"},
                    }
                ],
            )

    return [
        BenchmarkCase(
            name="simhash_dedup",
            description="SimHash dedup add_if_unique",
            run=_run_simhash,
        ),
        BenchmarkCase(
            name="keyword_score",
            description="Keyword scoring via ahocorasick",
            run=_run_keyword_score,
        ),
        BenchmarkCase(
            name="validation_result",
            description="ValidationResult model creation",
            run=_run_validation_result,
        ),
        BenchmarkCase(
            name="analysis_output",
            description="AnalysisOutput model creation",
            run=_run_analysis_output,
        ),
    ]


def _select_cases(
    cases: list[BenchmarkCase],
    selected: list[str],
) -> list[BenchmarkCase]:
    """Select cases."""
    if not selected or "all" in selected:
        return cases
    selected_set = {s.strip() for s in selected}
    return [case for case in cases if case.name in selected_set]


def _print_results(stats: list[BenchmarkStats]) -> None:
    """Log formatted benchmark results."""
    if not stats:
        logger.info("No benchmarks selected.")
        return

    headers = [
        "benchmark",
        "runs",
        "iters",
        "mean_ms",
        "mean_us/op",
        "min_us/op",
        "max_us/op",
        "ops/s",
    ]
    rows: list[list[str]] = []
    for result in stats:
        rows.append(
            [
                result.name,
                str(result.repeats),
                str(result.iterations),
                f"{result.mean_s * 1000:.2f}",
                f"{result.mean_per_op_us:.2f}",
                f"{result.min_per_op_us:.2f}",
                f"{result.max_per_op_us:.2f}",
                f"{result.ops_per_sec:,.0f}",
            ]
        )

    table = _format_table(headers, rows)
    logger.info("Benchmark Results:\n%s", table)


class BenchmarkConfig(BaseSettings):
    """CLI settings for benchmark profile runs."""

    model_config = SettingsConfigDict(
        cli_prog_name="bench",
        cli_exit_on_error=True,
        cli_implicit_flags=True,
        extra="ignore",
    )

    bench: list[str] = Field(
        default_factory=lambda: ["all"],
        description="Benchmarks to run (names or 'all')",
        json_schema_extra={"cli_args": {"nargs": "+", "action": "extend"}},
    )
    list_benchmarks: bool = Field(
        default=False,
        description="List benchmarks and exit",
        json_schema_extra={"cli_args": {"nargs": "?", "const": True}},
    )
    iterations: int = Field(
        default=2000,
        ge=1,
        description="Operations per benchmark run",
    )
    repeats: int = Field(
        default=5,
        ge=1,
        description="Number of runs per benchmark",
    )
    warmup: int = Field(
        default=1,
        ge=0,
        description="Warmup runs before measurement",
    )
    text_size: int = Field(
        default=200,
        ge=10,
        description="Text length for text-based benchmarks",
    )
    simhash_bits: int = Field(
        default=64,
        ge=32,
        le=128,
        description="SimHash bits for dedup benchmark",
    )
    simhash_max_distance: int = Field(
        default=3,
        ge=0,
        le=32,
        description="SimHash max distance for dedup benchmark",
    )
    seed: int = Field(
        default=0,
        ge=0,
        description="Random seed for deterministic inputs",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level",
    )

    def cli_cmd(self) -> None:
        setup_logging(level=self.log_level, format_type="simple")
        cases = _build_cases(self)
        if self.list_benchmarks:
            logger.info("Available benchmarks:")
            for case in cases:
                logger.info("  %s - %s", case.name, case.description)
            return

        selected = _select_cases(cases, self.bench)
        logger.info(
            "Running %d benchmark(s) (iters=%d, repeats=%d, warmup=%d)",
            len(selected),
            self.iterations,
            self.repeats,
            self.warmup,
        )
        stats = [
            _run_case(case, self.iterations, self.repeats, self.warmup)
            for case in selected
        ]
        _print_results(stats)


def main() -> None:
    """Run the command-line entrypoint."""
    CliApp.run(BenchmarkConfig)


if __name__ == "__main__":
    main()
