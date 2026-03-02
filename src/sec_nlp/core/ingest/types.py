# src/sec_nlp/core/ingest/types.py
"""Typed result models for SEC filing download and ingestion operations."""

from __future__ import annotations

from typing import TypedDict


class DownloadResult(TypedDict, total=False):
    """Per-symbol download counters and status fields."""

    success: bool
    downloaded: int
    skipped_existing: int
    form_type: str
    error: str


type DownloadResults = dict[str, DownloadResult]
