"""Writers for retrieve ranked results outputs."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.pipelines.output_io import (
    write_csv_metadata_comments,
    write_json,
    write_yaml,
)
from sec_nlp.types import JsonValue

from ...models import RetrievalHit


class RankedResultsPayload(BaseModel):
    """Root payload for JSON/YAML retrieve outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_timestamp: str
    run_short_id: int | None = None
    run_id: str
    run_short_id_display: str

    symbol: str
    queries: list[str] = Field(default_factory=list)
    hits: list[RetrievalHit] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


RANKED_COLUMNS: tuple[str, ...] = (
    "symbol",
    "query",
    "accession_number",
    "section_type",
    "section_number",
    "chunk_index",
    "form_type",
    "filed_date",
    "company_name",
    "cik",
    "score",
    "edgar_url",
    "snippet",
)


def write_ranked_results_csv(
    path: Path,
    hits: list[RetrievalHit],
    *,
    header_fields: Mapping[str, JsonValue] | None = None,
) -> None:
    """Write flat ranked hits to CSV."""

    with open(path, "w", encoding="utf-8", newline="") as handle:
        write_csv_metadata_comments(handle, header_fields)
        writer = csv.DictWriter(handle, fieldnames=list(RANKED_COLUMNS))
        writer.writeheader()

        for hit in hits:
            payload = hit.model_dump(mode="json")
            row = {column: payload.get(column) for column in RANKED_COLUMNS}
            writer.writerow(row)


def write_ranked_results_json(
    path: Path, payload: RankedResultsPayload
) -> None:
    """Write retrieve payload as JSON."""

    write_json(path, payload, exclude_none=True)


def write_ranked_results_yaml(
    path: Path, payload: RankedResultsPayload
) -> None:
    """Write retrieve payload as YAML."""

    write_yaml(path, payload, exclude_none=True, sort_keys=False)
