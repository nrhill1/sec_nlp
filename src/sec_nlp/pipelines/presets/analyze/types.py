# src/sec_nlp/pipelines/presets/analyze/types.py
"""Shared types for the analyze pipeline."""

from typing import TypedDict

type Timings = dict[str, float]


class ChunkStats(TypedDict, total=False):
    count: float
    min_value: float
    max_value: float
    median: float
    mean: float
    timings: Timings


class SymbolRunMetadata(TypedDict):
    outputs: int
    chunk_stats: ChunkStats


type RunMetadata = dict[str, SymbolRunMetadata | int]
