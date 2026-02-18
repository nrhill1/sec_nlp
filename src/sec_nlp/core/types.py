"""Type utilities for JSON coercion and runtime guards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeGuard

from sec_nlp.types import JsonDict, JsonObject, JsonValue


def is_json_object(value: JsonValue) -> TypeGuard[JsonObject]:
    """Return True if value is a mapping with string keys."""
    if not isinstance(value, Mapping):
        return False
    return all(isinstance(key, str) for key in value)


def is_json_mapping(value: JsonValue) -> TypeGuard[Mapping[str, JsonValue]]:
    """Alias for JSON mapping guards used in config parsing."""
    return is_json_object(value)


def mapping_to_json_dict(mapping: JsonObject) -> JsonDict:
    """Convert a JSON mapping to a mutable JsonDict."""
    return {key: mapping[key] for key in mapping}


def as_json_dict(value: JsonValue) -> JsonDict | None:
    """Coerce a JsonValue into a JsonDict if possible."""
    if not isinstance(value, Mapping):
        return None
    json_dict: JsonDict = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        normalized: JsonValue
        if isinstance(item, Mapping):
            nested = {}
            for mapping_key, mapping_value in item.items():
                if not isinstance(mapping_key, str):
                    return None
                nested[mapping_key] = mapping_value
            normalized = nested
        elif isinstance(item, Sequence) and not isinstance(item, str):
            normalized = list(item)
        elif isinstance(item, (str, int, float, bool)) or item is None:
            normalized = item
        else:
            return None
        json_dict[key] = normalized
    return json_dict


def coerce_json_dict(value: JsonValue) -> JsonDict | None:
    """Compatibility wrapper for JSON dict coercion."""
    return as_json_dict(value)


def coerce_json_value(value: JsonValue) -> JsonValue | None:
    """Normalize a JsonValue into a JSON-serializable shape."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Sequence) and not isinstance(value, str):
        items: list[JsonValue] = []
        for item in value:
            normalized = coerce_json_value(item)
            if normalized is None:
                return None
            items.append(normalized)
        return items
    if isinstance(value, Mapping):
        normalized_dict: JsonDict = {}
        for key, item in value.items():
            if not isinstance(key, str):
                return None
            normalized_item = coerce_json_value(item)
            if normalized_item is None:
                return None
            normalized_dict[key] = normalized_item
        return normalized_dict
    return None


def coerce_bool(value: JsonValue | None) -> bool | None:
    """Parse common boolean-like values into True/False."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in ("true", "false"):
            return cleaned == "true"
    return None


def coerce_float(value: JsonValue | None) -> float | None:
    """Parse numeric-like values into float when possible."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
