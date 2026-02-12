# src/sec_nlp/pipelines/presets/analyze/types.py
"""Shared types for the analyze pipeline."""

import threading
from typing import TypedDict

type Timings = dict[str, float]

# ---------------------------------------------------------------------------
# Graceful abort support
# ---------------------------------------------------------------------------
_abort_event = threading.Event()


def is_abort_requested() -> bool:
    """Check whether a graceful abort has been requested (Ctrl+C)."""
    return _abort_event.is_set()


class PrefetchedSymbolData(TypedDict):
    """Data prepared in a background thread for the next symbol."""

    docs: list  # list[Document] — avoids circular import
    allowed_accessions: set[str] | None
    timings: Timings
    preprocessed: bool


class ChunkStats(TypedDict, total=False):
    count: int
    min_value: float
    max_value: float
    median: float
    mean: float
    analyzed_count: int
    timings: Timings


class SymbolRunMetadata(TypedDict):
    outputs: int
    chunk_stats: ChunkStats


type RunMetadata = dict[str, SymbolRunMetadata | int]
