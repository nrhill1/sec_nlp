"""Spec loading and validation helpers for flow execution."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .models import FlowSpec


def load_flow_spec(spec_path: str | Path) -> FlowSpec:
    """Load and validate a flow spec from JSON or YAML."""
    path = Path(spec_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Flow spec not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.casefold()
    payload: object
    if suffix == ".json":
        payload = json.loads(raw_text)
    else:
        payload = yaml.safe_load(raw_text)

    if not isinstance(payload, dict):
        raise ValueError(f"Flow spec root must be an object mapping: {path}")
    return FlowSpec.model_validate(payload)
