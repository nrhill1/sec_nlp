"""Shared conversion utilities for flow stage runnables."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sec_nlp.app.flows.artifacts import ChatSeedBundle
from sec_nlp.app.flows.models import FlowDefaults
from sec_nlp.core.types import coerce_result_json_dict
from sec_nlp.types import JsonDict, JsonValue, ResultDict

type StageConfigValue = JsonValue | date | Path
type ChatStageConfigValue = StageConfigValue | ChatSeedBundle


def build_stage_defaults_payload(
    defaults: FlowDefaults,
) -> dict[str, StageConfigValue]:
    """Build stage config payload from flow defaults."""
    payload: dict[str, StageConfigValue] = {"email": defaults.email}
    if defaults.symbols:
        payload["symbols"] = list(defaults.symbols)
    if defaults.forms is not None:
        payload["forms"] = list(defaults.forms)
    if defaults.start_date is not None:
        payload["start_date"] = defaults.start_date
    if defaults.end_date is not None:
        payload["end_date"] = defaults.end_date
    if defaults.dl_path is not None:
        payload["dl_path"] = defaults.dl_path
    if defaults.out_path is not None:
        payload["out_path"] = defaults.out_path
    if defaults.dry_run is not None:
        payload["dry_run"] = defaults.dry_run
    return payload


def build_chat_defaults_payload(
    defaults: FlowDefaults,
) -> dict[str, ChatStageConfigValue]:
    """Build chat-stage payload with optional seeded context support."""
    base_payload = build_stage_defaults_payload(defaults)
    payload: dict[str, ChatStageConfigValue] = {}
    for key, value in base_payload.items():
        payload[key] = value
    return payload


def normalize_stage_metadata(metadata: ResultDict) -> JsonDict:
    """Normalize stage metadata into JSON-safe dictionary payload."""
    return coerce_result_json_dict(metadata)
