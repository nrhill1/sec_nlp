# src/sec_nlp/pipelines/serialization.py
"""Shared helpers for serialization and numeric normalization."""

from __future__ import annotations

from pydantic import BaseModel

from sec_nlp.types import JsonValue


def serialize_payload(
    data: JsonValue | BaseModel, *, exclude_none: bool = False
) -> JsonValue:
    """Normalize BaseModel outputs into JSON-compatible payloads once."""
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json", exclude_none=exclude_none)
    return data


def round_float(value: float | int | None, *, places: int) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def round_score(value: float | int | None) -> float | None:
    return round_float(value, places=2)


def round_timing(value: float | int | None) -> float | None:
    return round_float(value, places=3)


def is_score_key(key: str) -> bool:
    lowered = key.lower()
    return "score" in lowered or "confidence" in lowered or "overlap" in lowered
