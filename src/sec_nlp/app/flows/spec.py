# src/sec_nlp/app/flows/spec.py
"""Flow spec loader utilities for JSON/YAML ingress.

This module is the file-format boundary before model validation; it decodes
spec content and passes a mapping into `FlowSpec` so structural validation is
handled in one canonical location.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from sec_nlp.types import JsonValue

from .models import FlowSpec


def load_flow_spec(spec_path: str | Path) -> FlowSpec:
    """Load and validate a flow spec from JSON or YAML."""
    path = Path(spec_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Flow spec not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.casefold()
    parsed: JsonValue
    if suffix == ".json":
        parsed = json.loads(raw_text)
    else:
        parsed = yaml.safe_load(raw_text)

    if not isinstance(parsed, dict):
        raise ValueError(f"Flow spec root must be an object mapping: {path}")
    return FlowSpec.model_validate(parsed)
