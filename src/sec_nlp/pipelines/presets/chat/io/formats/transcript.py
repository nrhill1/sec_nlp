# src/sec_nlp/pipelines/presets/chat/io/formats/transcript.py
"""Writers for chat transcript outputs."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

from sec_nlp.pipelines.output_io import (
    write_csv_metadata_comments,
    write_json,
    write_yaml,
)
from sec_nlp.types import JsonValue

from ...models import ChatTranscriptPayload

_TRANSCRIPT_COLUMNS: tuple[str, ...] = (
    "turn_index",
    "role",
    "message",
    "citations",
)


def write_chat_transcript_csv(
    path: Path,
    payload: ChatTranscriptPayload,
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None:
    """Write chat transcript rows to CSV."""

    with open(path, "w", encoding="utf-8", newline="") as handle:
        write_csv_metadata_comments(handle, header_fields)
        writer = csv.DictWriter(handle, fieldnames=list(_TRANSCRIPT_COLUMNS))
        writer.writeheader()

        for idx, turn in enumerate(payload.turns, start=1):
            writer.writerow(
                {
                    "turn_index": idx,
                    "role": turn.role,
                    "message": turn.message,
                    "citations": " ".join(turn.citations),
                }
            )


def write_chat_transcript_json(
    path: Path, payload: ChatTranscriptPayload
) -> None:
    """Write chat transcript payload as JSON."""

    write_json(path, payload, exclude_none=True)


def write_chat_transcript_yaml(
    path: Path, payload: ChatTranscriptPayload
) -> None:
    """Write chat transcript payload as YAML."""

    write_yaml(path, payload, exclude_none=True, sort_keys=False)
