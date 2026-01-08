import time
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TypedDict

from _typeshed import Incomplete
from tqdm import tqdm

@dataclass
class PhaseStats:
    name: str
    total: int = ...
    completed: int = ...
    failed: int = ...
    start_time: float = field(default_factory=time.time)
    end_time: float | None = ...
    @property
    def success_rate(self) -> float: ...
    @property
    def duration(self) -> float: ...
    @property
    def items_per_second(self) -> float: ...
    @property
    def eta_seconds(self) -> float | None: ...

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
    total_symbols: Incomplete
    show_progress: Incomplete
    start_time: Incomplete
    phases: dict[str, PhaseStats]
    current_phase: str | None
    symbols_completed: int
    chunks_processed: int
    chunks_relevant: int
    errors: list[str]
    def __init__(
        self, total_symbols: int = 0, show_progress: bool = True
    ) -> None: ...
    def start_phase(self, name: str, total: int = 0) -> PhaseStats: ...
    def update_phase(
        self, completed: int = 0, failed: int = 0, increment: bool = True
    ) -> None: ...
    def end_phase(self) -> PhaseStats | None: ...
    def add_error(self, error: str) -> None: ...
    def symbol_complete(self, chunks: int = 0, relevant: int = 0) -> None: ...
    @property
    def overall_eta(self) -> float | None: ...
    @property
    def elapsed_time(self) -> float: ...
    def get_summary(self) -> ProgressSummary: ...
    def format_eta(self, seconds: float | None) -> str: ...
    def print_status(self) -> None: ...

@contextmanager
def progress_bar[T](
    iterable: Iterable[T],
    desc: str = "",
    total: int | None = None,
    unit: str = "it",
    tracker: ProgressTracker | None = None,
    phase_name: str | None = None,
) -> Generator[tqdm[T]]: ...
def format_duration(seconds: float) -> str: ...
def print_final_summary(tracker: ProgressTracker) -> None: ...
