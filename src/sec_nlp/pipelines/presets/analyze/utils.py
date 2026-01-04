# src/sec_nlp/pipelines/presets/analyze/utils.py
"""Shared helpers for analyze pipeline modules."""

from __future__ import annotations

from sec_nlp.pipelines.types import MetadataMap


def resolve_symbol_for_output(
    fallback_symbol: str, *metas: MetadataMap | None
) -> str:
    """Pick the symbol to use for output routing, preferring metadata."""
    for meta in metas:
        if not meta:
            continue
        symbol = meta.get("symbol") or meta.get("ticker")
        if symbol:
            return str(symbol).strip().upper()

    return fallback_symbol.strip().upper()
