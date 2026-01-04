"""Typed results for SEC filing downloads."""

from __future__ import annotations

from typing import TypedDict


class DownloadResult(TypedDict, total=False):
    success: bool
    downloaded: int
    skipped_existing: int
    form_type: str
    error: str


type DownloadResults = dict[str, DownloadResult]
