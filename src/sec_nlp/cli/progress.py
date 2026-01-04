# src/sec_nlp/cli/progress.py
"""Enhanced progress tracking with ETA for the CLI."""

import sys
import time
from collections.abc import Generator, Iterable, Sized
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TypedDict

from tqdm import tqdm


@dataclass
class PhaseStats:
    """Statistics for a processing phase."""

    name: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.completed == 0:
            return 0.0
        return (self.completed - self.failed) / self.completed

    @property
    def duration(self) -> float:
        """Get phase duration in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def items_per_second(self) -> float:
        """Calculate processing rate."""
        if self.duration == 0:
            return 0.0
        return self.completed / self.duration

    @property
    def eta_seconds(self) -> float | None:
        """Estimate time remaining."""
        if self.completed == 0 or self.total == 0:
            return None
        remaining = self.total - self.completed
        rate = self.items_per_second
        if rate == 0:
            return None
        return remaining / rate


class SymbolSummary(TypedDict):
    total: int
    completed: int
    remaining: int


class ChunkSummary(TypedDict):
    processed: int
    relevant: int


class TimingSummary(TypedDict):
    elapsed_seconds: float
    eta_seconds: float | None


class PhaseSummary(TypedDict):
    completed: int
    failed: int
    duration: float
    rate: float


class ProgressSummary(TypedDict):
    symbols: SymbolSummary
    chunks: ChunkSummary
    timing: TimingSummary
    errors: int
    phases: dict[str, PhaseSummary]


class ProgressTracker:
    """Enhanced progress tracker with phase management and ETA."""

    def __init__(self, total_symbols: int = 0, show_progress: bool = True):
        """Initialize progress tracker.

        Args:
            total_symbols: Total number of symbols to process
            show_progress: Whether to show progress bars
        """
        self.total_symbols = total_symbols
        self.show_progress = show_progress and sys.stdout.isatty()
        self.start_time = time.time()

        # Phase tracking
        self.phases: dict[str, PhaseStats] = {}
        self.current_phase: str | None = None

        # Overall stats
        self.symbols_completed = 0
        self.chunks_processed = 0
        self.chunks_relevant = 0
        self.errors: list[str] = []

    def start_phase(self, name: str, total: int = 0) -> PhaseStats:
        """Start a new processing phase.

        Args:
            name: Phase name (e.g., "downloading", "analyzing", "storing")
            total: Total items to process in this phase

        Returns:
            PhaseStats object for the phase
        """
        stats = PhaseStats(name=name, total=total)
        self.phases[name] = stats
        self.current_phase = name
        return stats

    def update_phase(
        self,
        completed: int = 0,
        failed: int = 0,
        increment: bool = True,
    ) -> None:
        """Update current phase progress.

        Args:
            completed: Number of items completed (or increment)
            failed: Number of items failed (or increment)
            increment: If True, add to existing counts; otherwise set absolute values
        """
        if self.current_phase is None:
            return

        stats = self.phases[self.current_phase]
        if increment:
            stats.completed += completed
            stats.failed += failed
        else:
            stats.completed = completed
            stats.failed = failed

    def end_phase(self) -> PhaseStats | None:
        """End the current phase.

        Returns:
            Final PhaseStats for the phase, or None if no phase active
        """
        if self.current_phase is None:
            return None

        stats = self.phases[self.current_phase]
        stats.end_time = time.time()
        self.current_phase = None
        return stats

    def add_error(self, error: str) -> None:
        """Record an error."""
        self.errors.append(error)

    def symbol_complete(self, chunks: int = 0, relevant: int = 0) -> None:
        """Mark a symbol as complete.

        Args:
            chunks: Number of chunks processed for this symbol
            relevant: Number of relevant chunks found
        """
        self.symbols_completed += 1
        self.chunks_processed += chunks
        self.chunks_relevant += relevant

    @property
    def overall_eta(self) -> float | None:
        """Estimate overall time remaining."""
        if self.symbols_completed == 0 or self.total_symbols == 0:
            return None
        elapsed = time.time() - self.start_time
        rate = self.symbols_completed / elapsed
        remaining = self.total_symbols - self.symbols_completed
        if rate == 0:
            return None
        return remaining / rate

    @property
    def elapsed_time(self) -> float:
        """Get total elapsed time."""
        return time.time() - self.start_time

    def get_summary(self) -> ProgressSummary:
        """Get progress summary."""
        symbols: SymbolSummary = {
            "total": self.total_symbols,
            "completed": self.symbols_completed,
            "remaining": self.total_symbols - self.symbols_completed,
        }
        chunks: ChunkSummary = {
            "processed": self.chunks_processed,
            "relevant": self.chunks_relevant,
        }
        timing: TimingSummary = {
            "elapsed_seconds": self.elapsed_time,
            "eta_seconds": self.overall_eta,
        }
        phases: dict[str, PhaseSummary] = {}
        for name, stats in self.phases.items():
            phase_summary: PhaseSummary = {
                "completed": stats.completed,
                "failed": stats.failed,
                "duration": stats.duration,
                "rate": stats.items_per_second,
            }
            phases[name] = phase_summary
        summary: ProgressSummary = {
            "symbols": symbols,
            "chunks": chunks,
            "timing": timing,
            "errors": len(self.errors),
            "phases": phases,
        }
        return summary

    def format_eta(self, seconds: float | None) -> str:
        """Format ETA in human-readable format."""
        if seconds is None:
            return "calculating..."
        if seconds < 60:
            return f"{int(seconds)}s"
        if seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

    def print_status(self) -> None:
        """Print current status to console."""
        eta_str = self.format_eta(self.overall_eta)
        elapsed_str = self.format_eta(self.elapsed_time)

        status_parts = [
            f"Symbols: {self.symbols_completed}/{self.total_symbols}",
            f"Chunks: {self.chunks_processed} ({self.chunks_relevant} relevant)",
            f"Elapsed: {elapsed_str}",
            f"ETA: {eta_str}",
        ]

        if self.errors:
            status_parts.append(f"Errors: {len(self.errors)}")

        print(" | ".join(status_parts), end="\r")


@contextmanager
def progress_bar[T](
    iterable: Iterable[T],
    desc: str = "",
    total: int | None = None,
    unit: str = "it",
    tracker: ProgressTracker | None = None,
    phase_name: str | None = None,
) -> Generator[tqdm[T]]:
    """Context manager for progress bar with tracker integration.

    Args:
        iterable: Iterable to wrap
        desc: Description for progress bar
        total: Total count (auto-detected if iterable has len)
        unit: Unit name for items
        tracker: Optional ProgressTracker to update
        phase_name: Optional phase name to track

    Yields:
        tqdm progress bar instance
    """
    if total is None and isinstance(iterable, Sized):
        total = len(iterable)

    if tracker and phase_name:
        tracker.start_phase(phase_name, total or 0)

    bar_format = (
        "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
    )

    pbar = tqdm(
        iterable,
        desc=desc,
        total=total,
        unit=unit,
        colour="cyan",
        leave=False,
        bar_format=bar_format,
    )

    try:
        yield pbar
    finally:
        pbar.close()
        if tracker and phase_name:
            tracker.end_phase()


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string like "1h 23m 45s"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}h {minutes}m {secs}s"


def print_final_summary(tracker: ProgressTracker) -> None:
    """Print final processing summary.

    Args:
        tracker: ProgressTracker with results
    """
    summary = tracker.get_summary()
    timing = summary["timing"]
    assert isinstance(timing, dict)
    elapsed_seconds = timing["elapsed_seconds"]
    assert isinstance(elapsed_seconds, (int, float))
    elapsed = format_duration(elapsed_seconds)

    print("\n" + "=" * 50)
    print("Processing Complete")
    print("=" * 50)
    print(
        f"  Symbols processed: {summary['symbols']['completed']}/{summary['symbols']['total']}"
    )
    print(f"  Chunks analyzed:   {summary['chunks']['processed']}")
    print(f"  Relevant chunks:   {summary['chunks']['relevant']}")
    print(f"  Total time:        {elapsed}")

    if summary["errors"] > 0:
        print(f"  Errors:            {summary['errors']}")

    # Phase breakdown
    if summary["phases"]:
        print("\nPhase breakdown:")
        for name, stats in summary["phases"].items():
            duration = format_duration(stats["duration"])
            print(
                f"  {name}: {stats['completed']} items in {duration} ({stats['rate']:.1f}/s)"
            )

    print("=" * 50)
